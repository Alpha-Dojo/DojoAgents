"""Integration tests: full SSE round-trip through /api/chat."""

from __future__ import annotations

import anyio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
import pytest


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


def _stream_response(agent, payload):
    """Run a streaming request with the application's lifespan active."""

    with TestClient(_make_app(agent)) as client:
        with client.stream("POST", "/api/chat", json=payload) as response:
            lines = [line.strip() for line in response.iter_lines() if line.strip()]
            return response.status_code, dict(response.headers), lines


def _route_endpoint(app, path, method="GET"):
    return next(
        route.endpoint
        for route in app.routes
        if getattr(route, "path", None) == path and method in getattr(route, "methods", set())
    )


@pytest.mark.anyio
async def test_chat_sse_disconnect_closes_generator_from_another_task():
    """A Starlette disconnect task may close the body iterator it did not enter."""

    started = anyio.Event()
    cancelled = anyio.Event()

    class HangingAgent(FakeStreamingAgent):
        async def run(self, request, *, event_sink=None):
            started.set()
            try:
                await anyio.sleep_forever()
            finally:
                cancelled.set()

    app = _make_app(HangingAgent())
    async with app.router.lifespan_context(app):
        endpoint = _route_endpoint(app, "/api/chat", "POST")
        response = await endpoint(
            {
                "model": "test-model",
                "messages": [{"role": "user", "content": "hold"}],
                "stream": True,
                "metadata": {"session_id": "disconnect-chat"},
            }
        )
        body = response.body_iterator
        assert (await body.__anext__()).startswith("data: ")
        with anyio.fail_after(1.0):
            await started.wait()

        errors: list[BaseException] = []

        async def disconnect() -> None:
            try:
                await body.aclose()
            except BaseException as exc:  # capture the exact cross-task regression
                errors.append(exc)

        async with anyio.create_task_group() as disconnect_tasks:
            disconnect_tasks.start_soon(disconnect)
        with anyio.fail_after(1.0):
            await cancelled.wait()

        assert errors == []


@pytest.mark.anyio
async def test_persisted_sse_disconnect_closes_generator_from_another_task():
    """Persisted-event producers are app-owned and cancel cleanly on disconnect."""

    second_read_started = anyio.Event()
    producer_cancelled = anyio.Event()

    class PersistedService:
        def __init__(self) -> None:
            self.read_count = 0

        async def get_run(self, _principal, _run_id):
            return SimpleNamespace(status="running")

        async def read_events(self, _principal, _run_id, *, after_seq, limit):
            assert limit == 200
            self.read_count += 1
            if self.read_count == 1:
                event = SimpleNamespace(sequence=1, event_type="delta", payload={"text": "ready"})
                return SimpleNamespace(items=(event,))
            second_read_started.set()
            try:
                await anyio.sleep_forever()
            finally:
                producer_cancelled.set()

    runtime = FakeRuntime()
    runtime.session_service = PersistedService()
    from dojoagents.dashboard.server import create_app
    from dojoagents.sessions.models import SessionPrincipal

    app = create_app(runtime)
    async with app.router.lifespan_context(app):
        endpoint = _route_endpoint(app, "/api/chat/runs/{run_id}/events", "GET")
        response = await endpoint("run-disconnect", 0, SessionPrincipal("alice"))
        body = response.body_iterator
        assert "ready" in await body.__anext__()
        with anyio.fail_after(1.0):
            await second_read_started.wait()

        errors: list[BaseException] = []

        async def disconnect() -> None:
            try:
                await body.aclose()
            except BaseException as exc:  # capture the exact cross-task regression
                errors.append(exc)

        async with anyio.create_task_group() as disconnect_tasks:
            disconnect_tasks.start_soon(disconnect)
        with anyio.fail_after(1.0):
            await producer_cancelled.wait()

        assert errors == []


def test_sse_streaming_full_round_trip():
    """Full SSE flow: request with stream=true, receive OpenAI-compatible chunks."""
    agent = FakeStreamingAgent(chunks=["BTC ", "is ", "up"])
    status_code, headers, lines = _stream_response(
        agent,
        {
            "model": "gpt-4.1",
            "messages": [{"role": "user", "content": "analyze BTC"}],
            "stream": True,
            "user": "user-001",
            "metadata": {"session_id": "sess-int"},
        },
    )
    assert status_code == 200
    assert "text/event-stream" in headers.get("content-type", "")

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
    _, _, lines = _stream_response(
        agent,
        {
            "model": "test-model",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
            "metadata": {"session_id": "s1"},
        },
    )

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

    _stream_response(
        agent,
        {
            "model": "m",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
            "metadata": {"session_id": "s"},
        },
    )

    assert not hasattr(agent, "stream_delta_callback")


def test_dojo_v2_stream_emits_phase_event():
    agent = FakeStreamingAgent(chunks=["phase"])
    _, _, lines = _stream_response(
        agent,
        {
            "model": "gpt-4.1",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
            "metadata": {"session_id": "s1", "event_format": "dojo.v2"},
        },
    )

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

    _, _, lines = _stream_response(
        ToolAgent(),
        {
            "model": "gpt-4.1",
            "messages": [{"role": "user", "content": "create portfolio"}],
            "stream": True,
            "metadata": {"session_id": "s1", "event_format": "dojo.v2"},
        },
    )

    data_lines = [l for l in lines if l.startswith("data:") and "[DONE]" not in l]  # noqa
    events = [json.loads(dl.replace("data: ", "", 1)).get("dojo_event") for dl in data_lines]
    tool_start = next(event for event in events if event and event.get("type") == "tool_start")
    tool_result = next(event for event in events if event and event.get("type") == "tool_result")
    assert tool_start["call_id"] == "call-123"
    assert tool_result["call_id"] == "call-123"


def test_dojo_v2_stream_tool_result_includes_viz_blocks():
    viz_blocks = [
        {
            "id": "viz-1",
            "kind": "quote_card",
            "title": "AAPL",
            "subtitle": None,
            "source_tool": "agent_viz_build",
            "truncated": False,
            "payload": {"ticker": "AAPL", "last_price": 200},
        }
    ]

    class VizAgent(FakeStreamingAgent):
        async def run(self, request, *, event_sink=None):
            from dojoagents.agent.models import AgentResponse

            if event_sink:
                event_sink.tool_start(
                    call_id="call-viz",
                    tool="agent_viz_build",
                    arguments={"mapping_hint": "ticker_quote"},
                )
                event_sink.tool_result(
                    call_id="call-viz",
                    tool="agent_viz_build",
                    ok=True,
                    content="Built 1 visualization block(s): quote_card",
                    latency_ms=8,
                    data={"block_count": 1, "kinds": ["quote_card"]},
                    viz_blocks=viz_blocks,
                )
                event_sink.done(
                    model_id="fake-model",
                    tool_trace=[
                        {
                            "call_id": "call-viz",
                            "tool": "agent_viz_build",
                            "ok": True,
                            "viz_blocks": viz_blocks,
                        }
                    ],
                    tool_steps=1,
                )
            return AgentResponse(
                content="done",
                session_id=request.session_id,
                metadata={"usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3}},
            )

    _, _, lines = _stream_response(
        VizAgent(),
        {
            "model": "gpt-4.1",
            "messages": [{"role": "user", "content": "visualize AAPL"}],
            "stream": True,
            "metadata": {"session_id": "s1", "event_format": "dojo.v2"},
        },
    )

    data_lines = [l for l in lines if l.startswith("data:") and "[DONE]" not in l]  # noqa
    events = [json.loads(dl.replace("data: ", "", 1)).get("dojo_event") for dl in data_lines]
    tool_result = next(event for event in events if event and event.get("type") == "tool_result")
    done = next(event for event in events if event and event.get("type") == "done")
    assert tool_result["viz_blocks"] == viz_blocks
    assert done["tool_trace"][0]["viz_blocks"] == viz_blocks
