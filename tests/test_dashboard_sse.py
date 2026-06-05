"""Tests for SSE streaming module (TDD)."""
from __future__ import annotations

import asyncio
import json

import pytest


# ── make_stream_delta_callback ─────────────────────────────────────


@pytest.mark.asyncio
async def test_make_stream_delta_callback_puts_on_queue():
    from dojoagents.dashboard.sse import make_stream_delta_callback

    queue: asyncio.Queue = asyncio.Queue()
    callback = make_stream_delta_callback(queue)

    callback("hello")
    callback(" world")

    # call_soon_threadsafe defers to the event loop, so yield control
    await asyncio.sleep(0)

    assert queue.get_nowait() == "hello"
    assert queue.get_nowait() == " world"


@pytest.mark.asyncio
async def test_make_stream_delta_callback_returns_callable():
    from dojoagents.dashboard.sse import make_stream_delta_callback

    queue: asyncio.Queue = asyncio.Queue()
    callback = make_stream_delta_callback(queue)

    assert callable(callback)


# ── stream_completion_chunks ───────────────────────────────────────


@pytest.mark.asyncio
async def test_stream_completion_chunks_yields_openai_sequence():
    from dojoagents.dashboard.sse import stream_completion_chunks

    queue: asyncio.Queue = asyncio.Queue()
    # Feed deltas then sentinel
    queue.put_nowait("Hello ")
    queue.put_nowait("world!")
    queue.put_nowait(None)  # sentinel

    lines = []
    async for line in stream_completion_chunks(
        queue, model="gpt-4.1", completion_id="chatcmpl-test", created=1000,
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

    queue: asyncio.Queue = asyncio.Queue()
    queue.put_nowait(None)  # sentinel immediately

    lines = []
    async for line in stream_completion_chunks(
        queue, model="gpt-4.1", completion_id="chatcmpl-empty", created=2000,
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

    queue: asyncio.Queue = asyncio.Queue()
    # Push a dict (tool_call delta) then sentinel
    queue.put_nowait({
        "tool_calls": [{
            "index": 0,
            "id": "call_1",
            "type": "function",
            "function": {"name": "get_kline", "arguments": "{}"},
        }]
    })
    queue.put_nowait(None)

    lines = []
    async for line in stream_completion_chunks(
        queue, model="gpt-4.1", completion_id="chatcmpl-tool", created=3000,
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

    queue: asyncio.Queue = asyncio.Queue()
    queue.put_nowait(ValueError("test error"))

    with pytest.raises(ValueError, match="test error"):
        async for _line in stream_completion_chunks(
            queue, model="gpt-4.1", completion_id="chatcmpl-err", created=4000,
        ):
            pass


@pytest.mark.asyncio
async def test_stream_chunks_auto_generates_id_and_created():
    from dojoagents.dashboard.sse import stream_completion_chunks

    queue: asyncio.Queue = asyncio.Queue()
    queue.put_nowait(None)

    lines = []
    async for line in stream_completion_chunks(queue, model="gpt-4.1"):
        lines.append(line)

    data_lines = [l for l in lines if l.startswith("data: ")]
    first = json.loads(data_lines[0][6:])
    assert first["id"].startswith("chatcmpl-dojo-")
    assert isinstance(first["created"], int)
    assert first["created"] > 0
