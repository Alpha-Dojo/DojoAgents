"""SSE streaming module for OpenAI-compatible chat completion chunks."""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, AsyncGenerator, Callable


def make_stream_delta_callback(queue: asyncio.Queue) -> Callable[[Any], None]:
    """Return a sync callable that puts text deltas on an asyncio.Queue.

    Thread-safe: uses ``loop.call_soon_threadsafe`` when called from a
    different thread than the running event loop.
    """

    def callback(delta: Any) -> None:
        try:
            loop = asyncio.get_running_loop()
            loop.call_soon_threadsafe(queue.put_nowait, delta)
        except RuntimeError:
            pass

    return callback


def _make_chunk_line(
    completion_id: str,
    created: int,
    model: str,
    choice_delta: dict[str, Any],
) -> str:
    from dojoagents.agent.models import ChatCompletionChunk

    chunk = ChatCompletionChunk(
        id=completion_id,
        object="chat.completion.chunk",
        created=created,
        model=model,
        choices=[
            {
                "index": 0,
                **choice_delta,
            }
        ],
    )
    return chunk.to_sse_line()


async def stream_completion_chunks(
    queue: asyncio.Queue,
    *,
    model: str,
    completion_id: str | None = None,
    created: int | None = None,
) -> AsyncGenerator[str, None]:
    """Async generator that drains *queue* and yields OpenAI-compatible SSE lines.

    The queue receives items from ``make_stream_delta_callback``:
    - ``str``   → text content delta
    - ``dict``  → tool_calls delta (passed through to choices[0].delta)
    - ``None``  → sentinel: stop streaming
    - ``Exception`` → re-raised
    """
    completion_id = completion_id or f"chatcmpl-dojo-{uuid.uuid4().hex[:8]}"
    created = created or int(time.time())

    # 1. message_start
    yield _make_chunk_line(
        completion_id,
        created,
        model,
        {"delta": {"role": "assistant", "content": ""}, "finish_reason": None},
    )

    # 2. Drain queue for content_delta / tool_call_delta
    while True:
        item = await queue.get()
        if item is None:
            break
        if isinstance(item, Exception):
            raise item
        if isinstance(item, str):
            yield _make_chunk_line(
                completion_id,
                created,
                model,
                {"delta": {"content": item}, "finish_reason": None},
            )
        elif isinstance(item, dict):
            yield _make_chunk_line(
                completion_id,
                created,
                model,
                {"delta": item, "finish_reason": None},
            )

    # 3. message_end
    yield _make_chunk_line(
        completion_id,
        created,
        model,
        {"delta": {}, "finish_reason": "stop"},
    )

    # 4. [DONE] sentinel
    from dojoagents.agent.models import ChatCompletionChunk

    yield ChatCompletionChunk.done_sentinel()
