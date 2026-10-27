"""Tests for SSE streaming module (TDD)."""
from __future__ import annotations

import anyio
import json
import threading

import pytest


# ── app-owned producer lifecycle ───────────────────────────────────


@pytest.mark.anyio
async def test_owned_sse_producer_closes_cleanly_from_another_task():
    from dojoagents.dashboard.sse import start_owned_sse_producer

    entered = anyio.Event()
    cleaned_up = anyio.Event()

    async def produce() -> None:
        entered.set()
        try:
            await anyio.sleep_forever()
        finally:
            cleaned_up.set()

    async with anyio.create_task_group() as app_tasks:
        producer = await start_owned_sse_producer(app_tasks, produce, name="test-sse")
        await entered.wait()

        async def response_body():
            try:
                yield "data: ready\n\n"
            finally:
                assert await producer.stop(timeout=1.0)

        body = response_body()
        assert await body.__anext__() == "data: ready\n\n"

        async def disconnect() -> None:
            await body.aclose()

        app_tasks.start_soon(disconnect)
        with anyio.fail_after(1.0):
            await cleaned_up.wait()
        app_tasks.cancel_scope.cancel()


# ── make_stream_delta_callback ─────────────────────────────────────


@pytest.mark.asyncio
async def test_make_stream_delta_callback_puts_on_queue():
    from dojoagents.dashboard.sse import SSEEventStream, make_stream_delta_callback

    stream = SSEEventStream(max_buffer_size=2)
    callback = make_stream_delta_callback(stream)

    async with anyio.from_thread.BlockingPortal() as portal:
        stream.bind_portal(portal)
        callback("hello")
        callback(" world")
        await stream.close()

    assert stream.receive_stream.receive_nowait() == "hello"
    assert stream.receive_stream.receive_nowait() == " world"


@pytest.mark.asyncio
async def test_make_stream_delta_callback_returns_callable():
    from dojoagents.dashboard.sse import SSEEventStream, make_stream_delta_callback

    callback = make_stream_delta_callback(SSEEventStream(max_buffer_size=1))

    assert callable(callback)


@pytest.mark.asyncio
async def test_sync_callback_fails_closed_when_same_loop_buffer_is_full():
    from dojoagents.dashboard.sse import (
        SSEEventStream,
        StreamBackpressureError,
        make_stream_delta_callback,
    )

    stream = SSEEventStream(max_buffer_size=1)
    callback = make_stream_delta_callback(stream)
    async with anyio.from_thread.BlockingPortal() as portal:
        stream.bind_portal(portal)
        callback("first")
        with pytest.raises(StreamBackpressureError, match="capacity=1"):
            callback("second")
        await stream.close()


@pytest.mark.asyncio
async def test_external_thread_callback_uses_portal_and_backpressure():
    from dojoagents.dashboard.sse import SSEEventStream, make_stream_delta_callback

    stream = SSEEventStream(max_buffer_size=1)
    callback = make_stream_delta_callback(stream)
    producer_done = threading.Event()

    def produce() -> None:
        callback("first")
        callback("second")
        producer_done.set()

    async with anyio.from_thread.BlockingPortal() as portal:
        stream.bind_portal(portal)
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(anyio.to_thread.run_sync, produce)
            await anyio.sleep(0.02)
            assert producer_done.is_set() is False
            assert await stream.receive_stream.receive() == "first"
            assert await stream.receive_stream.receive() == "second"
        await stream.close()


@pytest.mark.asyncio
async def test_late_sync_callback_after_close_is_ignored():
    from dojoagents.dashboard.sse import SSEEventStream, make_stream_delta_callback

    stream = SSEEventStream(max_buffer_size=1)
    callback = make_stream_delta_callback(stream)
    async with anyio.from_thread.BlockingPortal() as portal:
        stream.bind_portal(portal)
        await stream.close()
        callback("late")


# ── stream_completion_chunks ───────────────────────────────────────


@pytest.mark.asyncio
async def test_stream_completion_chunks_yields_openai_sequence():
    from dojoagents.dashboard.sse import stream_completion_chunks

    send_stream, receive_stream = anyio.create_memory_object_stream(max_buffer_size=2)
    send_stream.send_nowait("Hello ")
    send_stream.send_nowait("world!")
    await send_stream.aclose()

    lines = []
    async for line in stream_completion_chunks(
        receive_stream, model="gpt-4.1", completion_id="chatcmpl-test", created=1000,
    ):
        lines.append(line)

    # Parse all data lines
    data_lines = [l for l in lines if l.startswith("data: ")]
    assert len(data_lines) >= 4  # message_start + 2 content_delta + message_end + [DONE]

    # First: message_start
    first = json.loads(data_lines[0][6:])
    assert first["id"] == "chatcmpl-test"
    assert first["object"] == "chat.completion.chunk"
    assert first["choices"][0]["delta"]["role"] == "assistant"
    assert first["choices"][0]["delta"]["content"] == ""
    assert first["choices"][0]["finish_reason"] is None

    # Middle: content deltas
    second = json.loads(data_lines[1][6:])
    assert second["choices"][0]["delta"]["content"] == "Hello "
    assert second["choices"][0]["finish_reason"] is None

    third = json.loads(data_lines[2][6:])
    assert third["choices"][0]["delta"]["content"] == "world!"
    assert third["choices"][0]["finish_reason"] is None

    # Second-to-last: message_end
    end = json.loads(data_lines[3][6:])
    assert end["choices"][0]["delta"] == {}
    assert end["choices"][0]["finish_reason"] == "stop"

    # Last: [DONE]
    assert data_lines[-1] == "data: [DONE]\n"


@pytest.mark.asyncio
async def test_stream_chunks_empty_content():
    from dojoagents.dashboard.sse import stream_completion_chunks

    send_stream, receive_stream = anyio.create_memory_object_stream(max_buffer_size=1)
    await send_stream.aclose()

    lines = []
    async for line in stream_completion_chunks(
        receive_stream, model="gpt-4.1", completion_id="chatcmpl-empty", created=2000,
    ):
        lines.append(line)

    data_lines = [l for l in lines if l.startswith("data: ")]
    # message_start + message_end + [DONE] = 3
    assert len(data_lines) == 3

    # First is message_start
    first = json.loads(data_lines[0][6:])
    assert first["choices"][0]["delta"]["role"] == "assistant"

    # Second is message_end
    end = json.loads(data_lines[1][6:])
    assert end["choices"][0]["finish_reason"] == "stop"

    # Last is [DONE]
    assert data_lines[-1] == "data: [DONE]\n"


@pytest.mark.asyncio
async def test_stream_chunks_tool_calls_delta():
    from dojoagents.dashboard.sse import stream_completion_chunks

    send_stream, receive_stream = anyio.create_memory_object_stream(max_buffer_size=1)
    send_stream.send_nowait({
        "tool_calls": [{
            "index": 0,
            "id": "call_1",
            "type": "function",
            "function": {"name": "get_kline", "arguments": "{}"},
        }]
    })
    await send_stream.aclose()

    lines = []
    async for line in stream_completion_chunks(
        receive_stream, model="gpt-4.1", completion_id="chatcmpl-tool", created=3000,
    ):
        lines.append(line)

    data_lines = [l for l in lines if l.startswith("data: ")]
    # message_start + tool_call_delta + message_end + [DONE] = 4
    assert len(data_lines) == 4

    # The tool_call delta
    tool_chunk = json.loads(data_lines[1][6:])
    assert "tool_calls" in tool_chunk["choices"][0]["delta"]
    assert tool_chunk["choices"][0]["delta"]["tool_calls"][0]["function"]["name"] == "get_kline"


@pytest.mark.asyncio
async def test_stream_chunks_handles_exception_in_queue():
    from dojoagents.dashboard.sse import stream_completion_chunks

    send_stream, receive_stream = anyio.create_memory_object_stream(max_buffer_size=1)
    send_stream.send_nowait(ValueError("test error"))
    await send_stream.aclose()

    with pytest.raises(ValueError, match="test error"):
        async for _line in stream_completion_chunks(
            receive_stream, model="gpt-4.1", completion_id="chatcmpl-err", created=4000,
        ):
            pass


@pytest.mark.asyncio
async def test_stream_chunks_auto_generates_id_and_created():
    from dojoagents.dashboard.sse import stream_completion_chunks

    send_stream, receive_stream = anyio.create_memory_object_stream(max_buffer_size=1)
    await send_stream.aclose()

    lines = []
    async for line in stream_completion_chunks(receive_stream, model="gpt-4.1"):
        lines.append(line)

    data_lines = [l for l in lines if l.startswith("data: ")]
    first = json.loads(data_lines[0][6:])
    assert first["id"].startswith("chatcmpl-dojo-")
    assert isinstance(first["created"], int)
    assert first["created"] > 0
