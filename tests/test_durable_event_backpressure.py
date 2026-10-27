from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import anyio
import pytest

from dojoagents.agent.events import AgentEventSink
from dojoagents.agent.providers import OpenAICompatibleProvider
from dojoagents.agent.session_run import _DurableEventWriter
from dojoagents.sessions.errors import SessionLeaseLostError


class Coordinator:
    run_id = "burst"
    service = SimpleNamespace(config=SimpleNamespace(runtime=SimpleNamespace(event_batch_size=20)))

    def __init__(self, delay=0):
        self.delay = delay
        self.events = []

    async def append_events(self, events, *, flush=True):
        await anyio.sleep(self.delay)
        self.events.extend(events)

    async def flush(self):
        pass


@pytest.mark.anyio
@pytest.mark.parametrize("delay", [0, 0.002])
@pytest.mark.parametrize("kind", ["think_delta", "delta", "replay"])
async def test_burst_is_bounded_ordered_and_drained(delay, kind):
    sink = AgentEventSink(run_id="burst", session_id="s")
    coordinator = Coordinator(delay)
    with anyio.fail_after(5):
        async with anyio.create_task_group() as group:
            writer = _DurableEventWriter(coordinator, sink, group)
            for index in range(1000):
                await sink.wait_for_capacity()
                if kind == "think_delta":
                    sink.thinking_delta(str(index))
                elif kind == "replay":
                    sink.replay({"type": "delta", "text": str(index)})
                else:
                    sink.delta(str(index))
                assert writer._send_stream.statistics().current_buffer_used <= 32
            await writer.close()
    assert [payload["seq"] for _, payload in coordinator.events] == list(range(1, 1001))
    assert [payload["text"] for _, payload in coordinator.events] == [str(i) for i in range(1000)]
    assert not sink._capacity_waiters and not sink._listeners


@pytest.mark.anyio
async def test_wait_is_cancellable_and_close_drains_after_store_resumes():
    sink = AgentEventSink(run_id="burst", session_id="s")
    coordinator = Coordinator()
    release = anyio.Event()
    entered = anyio.Event()
    original = coordinator.append_events

    async def stalled(events, *, flush=True):
        entered.set()
        await release.wait()
        await original(events, flush=flush)

    coordinator.append_events = stalled
    with anyio.fail_after(5):
        async with anyio.create_task_group() as group:
            writer = _DurableEventWriter(coordinator, sink, group)
            sink.delta("first")
            await entered.wait()
            for i in range(28):
                sink.delta(str(i))
            with anyio.move_on_after(0.02) as scope:
                await sink.wait_for_capacity()
            assert scope.cancel_called
            release.set()
            await writer.close()
    assert len(coordinator.events) == 29


@pytest.mark.anyio
async def test_lease_loss_wakes_backpressure_waiter():
    sink = AgentEventSink(run_id="burst", session_id="s")
    coordinator = Coordinator()
    coordinator.append_events = AsyncMock(side_effect=SessionLeaseLostError("lost"))
    with anyio.fail_after(5):
        async with anyio.create_task_group() as group:
            writer = _DurableEventWriter(coordinator, sink, group)
            for i in range(28):
                sink.delta(str(i))
            with pytest.raises(SessionLeaseLostError, match="lost"):
                await sink.wait_for_capacity()
            await writer.close()


@pytest.mark.anyio
async def test_openai_reasoning_stream_applies_real_writer_backpressure():
    sink = AgentEventSink(run_id="burst", session_id="s")
    coordinator = Coordinator(0.002)

    async def chunks():
        for i in range(1000):
            delta = SimpleNamespace(reasoning_content=str(i), content=None, tool_calls=None)
            yield SimpleNamespace(choices=[SimpleNamespace(delta=delta)], usage=None)

    provider = OpenAICompatibleProvider(api_key="test", base_url="https://example.test")
    with anyio.fail_after(5):
        async with anyio.create_task_group() as group:
            writer = _DurableEventWriter(coordinator, sink, group)
            with patch("openai.AsyncOpenAI") as client:
                client.return_value.chat.completions.create = AsyncMock(return_value=chunks())
                client.return_value.close = AsyncMock()
                await provider.chat([], [], model="qwen", stream=True, stream_callback=lambda text: None, metadata={"_dojo_event_sink": sink})
            await writer.close()
    assert [event_type for event_type, _ in coordinator.events] == ["think_start", *["think_delta"] * 1000, "think_end"]


@pytest.mark.anyio
async def test_gemini_many_reasoning_parts_apply_backpressure():
    from dojoagents.agent.gemini_provider import _emit_stream_deltas

    sink = AgentEventSink(run_id="burst", session_id="s")
    coordinator = Coordinator(0.002)
    payload = {"candidates": [{"content": {"parts": [{"text": str(i), "thought": True} for i in range(1000)]}}]}
    with anyio.fail_after(5):
        async with anyio.create_task_group() as group:
            writer = _DurableEventWriter(coordinator, sink, group)
            started = await _emit_stream_deltas(payload, stream_callback=None, event_sink=sink, seen_text_lengths={}, seen_reasoning_lengths={}, reasoning_started=False)
            assert started
            await writer.close()
    assert len(coordinator.events) == 1001
    assert [payload["text"] for _, payload in coordinator.events[1:]] == [str(i) for i in range(1000)]


@pytest.mark.anyio
async def test_store_failure_is_propagated_instead_of_hanging():
    sink = AgentEventSink(run_id="burst", session_id="s")
    coordinator = Coordinator()
    coordinator.flush = AsyncMock(side_effect=RuntimeError("store unavailable"))
    with anyio.fail_after(5):
        with pytest.raises(BaseExceptionGroup) as error:
            async with anyio.create_task_group() as group:
                writer = _DurableEventWriter(coordinator, sink, group)
                for i in range(28):
                    sink.delta(str(i))
                while True:
                    await sink.wait_for_capacity()
                    sink.delta("pending")
    assert "store unavailable" in str(error.value.exceptions[0])
    assert coordinator.flush.await_count == 4
    assert isinstance(writer._error, RuntimeError)
