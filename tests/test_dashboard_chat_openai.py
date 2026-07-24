"""Tests for /api/chat OpenAI-compatible endpoint + CORS (TDD)."""

from __future__ import annotations

import base64
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

# ── Helpers ──────────────────────────────────────────────────────────


def _make_fake_runtime(agent_run=None):
    """Create a FakeRuntime with a mock agent."""

    class FakeAgent:
        async def run(self, request, *, event_sink=None):
            if agent_run:
                return await agent_run(request, event_sink=event_sink)
            from dojoagents.agent.models import AgentResponse

            if event_sink is not None:
                event_sink.phase("planning")
                event_sink.delta(f"reply:{request.message}")
                event_sink.done(model_id="fake-model", tool_trace=[], tool_steps=0)
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
    assert req.metadata["history"] == []


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
    from dojoagents.harnesses.built_in.financial.context import (
        FinancialContext,
        FinancialRequestContextCodec,
    )

    payload = {
        "model": "gpt-4.1",
        "messages": [{"role": "user", "content": "analyze BTC"}],
        "metadata": {
            "session_id": "sess-q",
            "quant": {"market": "crypto", "symbols": ["BTC-USD"], "timeframe": "1d"},
        },
    }
    req, info = _completion_request(
        payload,
        surface=FinancialRequestContextCodec(),
    )
    assert isinstance(req.quant, FinancialContext)
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
    assert req.metadata["event_format"] == "openai.v1"


def test_completion_request_promotes_history_from_messages():
    from dojoagents.dashboard.server import _completion_request

    payload = {
        "model": "gpt-4.1",
        "messages": [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "reply"},
            {"role": "user", "content": "second"},
        ],
        "metadata": {"session_id": "sess-1", "event_format": "dojo.v2"},
    }
    req, info = _completion_request(payload)
    assert req.message == "second"
    assert req.metadata["history"] == [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "reply"},
    ]
    assert info["event_format"] == "dojo.v2"


def test_sync_runtime_agent_from_config_uses_native_gemini_provider():
    from dojoagents.agent.gemini_provider import GeminiNativeProvider
    from dojoagents.config.models import AgentsConfig, LLMConfig, LLMProviderConfig, AgentConfig
    from dojoagents.dashboard.server import _sync_runtime_agent_from_config

    class FakeStore:
        def snapshot(self):
            return AgentsConfig(
                llm_provider=LLMConfig(
                    default="gemini",
                    providers={
                        "gemini": LLMProviderConfig(
                            model="gemini-2.5-pro",
                            base_url="https://generativelanguage.googleapis.com/v1beta/openai",
                            api_key="test-key",
                            api_key_env="GEMINI_API_KEY",
                        )
                    },
                ),
                agent=AgentConfig(model="gpt-4.1"),
            )

    class FakeAgent:
        def __init__(self):
            self.llm_provider = None
            self.provider_config = None
            self.config = AgentConfig(model="gpt-4.1")
            self.model_context_registry = None

    runtime = MagicMock()
    runtime.config_store = FakeStore()
    runtime.agent = FakeAgent()

    model = _sync_runtime_agent_from_config(runtime, "gemini")

    assert model == "gemini-2.5-pro"
    assert isinstance(runtime.agent.llm_provider, GeminiNativeProvider)


# ── Non-streaming /api/chat tests ────────────────────────────────────


def test_chat_non_streaming_returns_openai_format():
    """Non-streaming response includes OpenAI structure."""
    client = TestClient(_make_app())
    response = client.post(
        "/api/chat",
        json={
            "model": "gpt-4.1",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": False,
            "user": "u1",
            "metadata": {"session_id": "s1"},
        },
    )
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
    response = client.post(
        "/api/chat",
        json={
            "message": "hi",
            "user_id": "u",
            "session_id": "s",
            "channel": "dashboard",
        },
    )
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

    async def streaming_agent_run(request, *, event_sink=None):
        if event_sink is not None:
            event_sink.phase("planning")
            event_sink.delta("Hello ")
            event_sink.phase("answering")
            event_sink.delta("world")
            event_sink.done(model_id="gpt-4.1", tool_trace=[], tool_steps=0)
        return AgentResponse(
            content="Hello world",
            session_id=request.session_id,
            metadata={"usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7}},
        )

    client = TestClient(_make_app(_make_fake_runtime(agent_run=streaming_agent_run)))
    with client.stream(
        "POST",
        "/api/chat",
        json={
            "model": "gpt-4.1",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
            "user": "u1",
            "metadata": {"session_id": "s1"},
        },
    ) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")
        lines = []
        for line in response.iter_lines():
            if line:
                lines.append(line)
        assert any("chat.completion.chunk" in l for l in lines)  # noqa
        assert any("[DONE]" in l for l in lines)  # noqa


def test_chat_non_streaming_dojo_v2_extension():
    client = TestClient(_make_app())
    response = client.post(
        "/api/chat",
        json={
            "model": "gpt-4.1",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": False,
            "user": "u1",
            "metadata": {"session_id": "s1", "event_format": "dojo.v2"},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["dojo"]["schema_version"] == "2.0"
    assert body["dojo"]["events"][-1]["type"] == "done"


def test_chat_rejects_unsupported_image_input():
    from dojoagents.agent.model_context import ModelContextInfo
    from dojoagents.config.models import LLMProviderConfig

    class FakeModelContextRegistry:
        async def resolve_info(self, provider_name, provider_cfg):
            assert provider_name == "zhipu"
            assert provider_cfg.author == "z-ai"
            assert provider_cfg.model == "glm-5.2"
            return ModelContextInfo(
                context_window=1048576,
                input_modalities=("text",),
                output_modalities=("text",),
                canonical_slug="z-ai/glm-5.2-20260616",
                provider_model_id="z-ai/glm-5.2",
                author="z-ai",
                slug="glm-5.2",
            )

    runtime = _make_fake_runtime()
    runtime.agent.provider_config = LLMProviderConfig(model="glm-5.2", author="z-ai")
    runtime.agent.model_context_registry = FakeModelContextRegistry()
    runtime.agent.llm_provider = type("FakeProvider", (), {"name": "zhipu"})()
    client = TestClient(_make_app(runtime))
    data_url = "data:image/png;base64," + base64.b64encode(b"abc").decode("ascii")

    response = client.post(
        "/api/chat",
        json={
            "model": "zhipu",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "describe this"},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
            "stream": False,
            "metadata": {"session_id": "s-img"},
        },
    )

    assert response.status_code == 422
    assert "does not support input modalities: image" in response.json()["error"]


# ── CORS tests ───────────────────────────────────────────────────────


def test_cors_headers_present():
    """CORS middleware allows cross-origin requests."""
    client = TestClient(_make_app())
    response = client.options(
        "/api/chat",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code in (200, 204)
    assert "access-control-allow-origin" in response.headers


def test_cors_allows_common_headers():
    """CORS allows Content-Type and Authorization headers."""
    client = TestClient(_make_app())
    response = client.options(
        "/api/chat",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,authorization",
        },
    )
    assert response.status_code in (200, 204)
    allow_headers = response.headers.get("access-control-allow-headers", "")
    assert "content-type" in allow_headers.lower()
