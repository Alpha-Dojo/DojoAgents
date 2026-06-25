"""Integration tests: full SSE round-trip through /api/chat."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from fastapi.testclient import TestClient


class FakeStreamingAgent:
    """Agent that emits request-scoped events to simulate streaming."""

    def __init__(self, chunks=None):
        self._chunks = chunks or ["Hello ", "world", "!"]

    async def run(self, request, *, event_sink=None):
        from dojoagents.agent.models import AgentResponse

        if event_sink:
            event_sink.phase("planning")
            for chunk in self._chunks:
                event_sink.delta(chunk)
            event_sink.done(model_id="fake-model", tool_trace=[], tool_steps=0)
        full_text = "".join(self._chunks)
        return AgentResponse(
            content=full_text,
            session_id=request.session_id,
            metadata={
                "iterations": 1,
                "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
            },
        )


class FakeRuntime:
    def __init__(self, agent=None):
        self.agent = agent or FakeStreamingAgent()
        self.config_store = None
        self.extensions = MagicMock()
        self.extensions.status = MagicMock(return_value=[])
        self.scheduler = MagicMock()
        self.scheduler.list_jobs = MagicMock(return_value=[])


def _make_app(agent=None):
    from dojoagents.dashboard.server import create_app

    return create_app(FakeRuntime(agent))


def test_sse_streaming_full_round_trip():
    """Full SSE flow: request with stream=true, receive OpenAI-compatible chunks."""
    agent = FakeStreamingAgent(chunks=["BTC ", "is ", "up"])
    client = TestClient(_make_app(agent))

    with client.stream(
        "POST",
        "/api/chat",
        json={
            "model": "gpt-4.1",
            "messages": [{"role": "user", "content": "analyze BTC"}],
            "stream": True,
            "user": "user-001",
            "metadata": {"session_id": "sess-int"},
        },
    ) as response:
        assert response.status_code == 200
        content_type = response.headers.get("content-type", "")
        assert "text/event-stream" in content_type

        lines = []
        for line in response.iter_lines():
            if line.strip():
                lines.append(line.strip())

    data_lines = [l for l in lines if l.startswith("data:")]  # noqa
    assert len(data_lines) >= 4  # start + 3 deltas + end + [DONE]

    first = json.loads(data_lines[0].replace("data: ", "", 1))
    assert first["object"] == "chat.completion.chunk"
    assert first["choices"][0]["delta"]["role"] == "assistant"

    done_line = data_lines[-1]
    assert "[DONE]" in done_line

    end_data = json.loads(data_lines[-2].replace("data: ", "", 1))
    assert end_data["choices"][0]["finish_reason"] == "stop"

    content_chunks = []
    for dl in data_lines[1:-2]:
        parsed = json.loads(dl.replace("data: ", "", 1))
        delta = parsed["choices"][0]["delta"]
        if "content" in delta:
            content_chunks.append(delta["content"])
    assert "".join(content_chunks) == "BTC is up"


def test_sse_streaming_preserves_completion_id():
    """All SSE chunks share the same completion id."""
    agent = FakeStreamingAgent(chunks=["a", "b"])
    client = TestClient(_make_app(agent))

    with client.stream(
        "POST",
        "/api/chat",
        json={
            "model": "test-model",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
            "metadata": {"session_id": "s1"},
        },
    ) as response:
        lines = [l.strip() for l in response.iter_lines() if l.strip()]  # noqa

    data_lines = [l for l in lines if l.startswith("data:") and "[DONE]" not in l]  # noqa
    ids = set()
    for dl in data_lines:
        parsed = json.loads(dl.replace("data: ", "", 1))
        ids.add(parsed["id"])
    assert len(ids) == 1


def test_non_streaming_openai_json_response():
    """Non-streaming returns complete OpenAI JSON with usage."""
    agent = FakeStreamingAgent(chunks=["reply"])
    client = TestClient(_make_app(agent))

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

    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"]["content"] == "reply"
    assert body["choices"][0]["finish_reason"] == "stop"
    assert body["usage"]["prompt_tokens"] == 20
    assert body["usage"]["completion_tokens"] == 10
    assert body["usage"]["total_tokens"] == 30

    assert body["content"] == "reply"
    assert body["session_id"] == "s1"


def test_old_format_backward_compat_integration():
    """Old format payload works end-to-end through the API."""
    agent = FakeStreamingAgent(chunks=["ok"])
    client = TestClient(_make_app(agent))

    response = client.post(
        "/api/chat",
        json={
            "message": "test",
            "user_id": "u1",
            "session_id": "s1",
            "channel": "dashboard",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["content"] == "ok"
    assert body["session_id"] == "s1"
    assert body["object"] == "chat.completion"


def test_streaming_callback_restored_after_run():
    """Request-scoped streaming does not need to mutate shared callbacks."""
    agent = FakeStreamingAgent(chunks=["x"])

    client = TestClient(_make_app(agent))
    with client.stream(
        "POST",
        "/api/chat",
        json={
            "model": "m",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
            "metadata": {"session_id": "s"},
        },
    ) as response:
        for _ in response.iter_lines():
            pass

    assert not hasattr(agent, "stream_delta_callback")


def test_dojo_v2_stream_emits_phase_event():
    agent = FakeStreamingAgent(chunks=["phase"])
    client = TestClient(_make_app(agent))

    with client.stream(
        "POST",
        "/api/chat",
        json={
            "model": "gpt-4.1",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
            "metadata": {"session_id": "s1", "event_format": "dojo.v2"},
        },
    ) as response:
        lines = [l.strip() for l in response.iter_lines() if l.strip()]  # noqa

    data_lines = [l for l in lines if l.startswith("data:") and "[DONE]" not in l]  # noqa
    events = [json.loads(dl.replace("data: ", "", 1)).get("dojo_event") for dl in data_lines]
    assert any(event and event.get("type") == "phase" for event in events)


def test_dojo_v2_stream_tool_events_include_call_id():
    class ToolAgent(FakeStreamingAgent):
        async def run(self, request, *, event_sink=None):
            from dojoagents.agent.models import AgentResponse

            if event_sink:
                event_sink.phase("tools")
                event_sink.tool_start(
                    call_id="call-123",
                    tool="portfolio_write_create",
                    arguments={"name": "Quality"},
                )
                event_sink.tool_result(
                    call_id="call-123",
                    tool="portfolio_write_create",
                    ok=True,
                    content="created",
                    latency_ms=10,
                )
                event_sink.done(
                    model_id="fake-model",
                    tool_trace=[{"call_id": "call-123", "tool": "portfolio_write_create", "ok": True}],
                    tool_steps=1,
                )
            return AgentResponse(
                content="created",
                session_id=request.session_id,
                metadata={"usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3}},
            )

    client = TestClient(_make_app(ToolAgent()))
    with client.stream(
        "POST",
        "/api/chat",
        json={
            "model": "gpt-4.1",
            "messages": [{"role": "user", "content": "create portfolio"}],
            "stream": True,
            "metadata": {"session_id": "s1", "event_format": "dojo.v2"},
        },
    ) as response:
        lines = [l.strip() for l in response.iter_lines() if l.strip()]  # noqa

    data_lines = [l for l in lines if l.startswith("data:") and "[DONE]" not in l]  # noqa
    events = [json.loads(dl.replace("data: ", "", 1)).get("dojo_event") for dl in data_lines]
    tool_start = next(event for event in events if event and event.get("type") == "tool_start")
    tool_result = next(event for event in events if event and event.get("type") == "tool_result")
    assert tool_start["call_id"] == "call-123"
    assert tool_result["call_id"] == "call-123"
