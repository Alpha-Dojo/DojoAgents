"""Tests for /api/chat OpenAI-compatible endpoint + CORS (TDD)."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient


# ── Helpers ──────────────────────────────────────────────────────────

def _make_fake_runtime(agent_run=None):
    """Create a FakeRuntime with a mock agent."""
    class FakeAgent:
        async def run(self, request):
            if agent_run:
                return await agent_run(request)
            from dojoagents.agent.models import AgentResponse
            return AgentResponse(
                content=f"reply:{request.message}",
                session_id=request.session_id,
                metadata={"usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}},
            )

    class FakeRuntime:
        def __init__(self):
            self.agent = FakeAgent()
            self.config_store = None
            self.extensions = MagicMock()
            self.extensions.status = MagicMock(return_value=[])
            self.scheduler = MagicMock()
            self.scheduler.list_jobs = MagicMock(return_value=[])

    return FakeRuntime()


def _make_app(runtime=None):
    from dojoagents.dashboard.server import create_app
    return create_app(runtime or _make_fake_runtime())


# ── _completion_request() parsing tests ─────────────────────────────

def test_completion_request_new_format():
    """Parse OpenAI-format payload with 'messages' key."""
    from dojoagents.dashboard.server import _completion_request

    payload = {
        "model": "gpt-4.1",
        "messages": [{"role": "user", "content": "hello"}],
        "stream": False,
        "user": "user-001",
        "metadata": {"session_id": "sess-1", "channel": "dashboard"},
    }
    req, info = _completion_request(payload)
    assert req.message == "hello"
    assert req.user_id == "user-001"
    assert req.session_id == "sess-1"
    assert req.channel == "dashboard"
    assert info["stream"] is False
    assert info["model"] == "gpt-4.1"


def test_completion_request_old_format_backward_compat():
    """Parse legacy payload with 'message' key (backward compat)."""
    from dojoagents.dashboard.server import _completion_request

    payload = {
        "message": "hi",
        "user_id": "u1",
        "session_id": "s1",
        "channel": "dashboard",
    }
    req, info = _completion_request(payload)
    assert req.message == "hi"
    assert req.user_id == "u1"
    assert req.session_id == "s1"
    assert req.channel == "dashboard"
    assert info["stream"] is False


def test_completion_request_extracts_quant_from_metadata():
    """Quant context is extracted from metadata."""
    from dojoagents.dashboard.server import _completion_request
    from dojoagents.quant.context import QuantContext

    payload = {
        "model": "gpt-4.1",
        "messages": [{"role": "user", "content": "analyze BTC"}],
        "metadata": {
            "session_id": "sess-q",
            "quant": {"market": "crypto", "symbols": ["BTC-USD"], "timeframe": "1d"},
        },
    }
    req, info = _completion_request(payload)
    assert isinstance(req.quant, QuantContext)
    assert req.quant.market == "crypto"
    assert "BTC-USD" in req.quant.symbols


def test_completion_request_defaults():
    """Sensible defaults when optional fields are missing."""
    from dojoagents.dashboard.server import _completion_request

    payload = {
        "model": "gpt-4.1",
        "messages": [{"role": "user", "content": "test"}],
    }
    req, info = _completion_request(payload)
    assert info["stream"] is False
    assert req.channel == "dashboard"


# ── Non-streaming /api/chat tests ────────────────────────────────────

def test_chat_non_streaming_returns_openai_format():
    """Non-streaming response includes OpenAI structure."""
    client = TestClient(_make_app())
    response = client.post("/api/chat", json={
        "model": "gpt-4.1",
        "messages": [{"role": "user", "content": "hi"}],
        "stream": False,
        "user": "u1",
        "metadata": {"session_id": "s1"},
    })
    assert response.status_code == 200
    body = response.json()
    # OpenAI structure
    assert "id" in body
    assert body["object"] == "chat.completion"
    assert "choices" in body
    assert body["choices"][0]["message"]["content"] == "reply:hi"
    assert body["choices"][0]["finish_reason"] == "stop"
    # Backward-compat fields
    assert body["content"] == "reply:hi"
    assert body["session_id"] == "s1"


def test_chat_old_format_backward_compat():
    """Old format payload still works and returns backward-compat fields."""
    client = TestClient(_make_app())
    response = client.post("/api/chat", json={
        "message": "hi",
        "user_id": "u",
        "session_id": "s",
        "channel": "dashboard",
    })
    assert response.status_code == 200
    body = response.json()
    # Backward-compat: legacy fields present
    assert body["content"] == "reply:hi"
    assert body["session_id"] == "s"
    # OpenAI structure also present
    assert body["object"] == "chat.completion"
    assert "choices" in body


# ── Streaming /api/chat tests ────────────────────────────────────────

def test_chat_streaming_returns_sse():
    """Streaming response returns SSE with correct content-type."""
    from dojoagents.agent.models import AgentResponse

    async def streaming_agent_run(request):
        return AgentResponse(
            content="Hello world",
            session_id=request.session_id,
            metadata={"usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7}},
        )

    client = TestClient(_make_app(_make_fake_runtime(agent_run=streaming_agent_run)))
    with client.stream("POST", "/api/chat", json={
        "model": "gpt-4.1",
        "messages": [{"role": "user", "content": "hi"}],
        "stream": True,
        "user": "u1",
        "metadata": {"session_id": "s1"},
    }) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")
        lines = []
        for line in response.iter_lines():
            if line:
                lines.append(line)
        assert any("chat.completion.chunk" in l for l in lines)
        assert any("[DONE]" in l for l in lines)


# ── CORS tests ───────────────────────────────────────────────────────

def test_cors_headers_present():
    """CORS middleware allows cross-origin requests."""
    client = TestClient(_make_app())
    response = client.options("/api/chat", headers={
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "POST",
    })
    assert response.status_code in (200, 204)
    assert "access-control-allow-origin" in response.headers


def test_cors_allows_common_headers():
    """CORS allows Content-Type and Authorization headers."""
    client = TestClient(_make_app())
    response = client.options("/api/chat", headers={
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type,authorization",
    })
    assert response.status_code in (200, 204)
    allow_headers = response.headers.get("access-control-allow-headers", "")
    assert "content-type" in allow_headers.lower()
