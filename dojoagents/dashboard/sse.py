"""SSE streaming module for OpenAI-compatible chat completion chunks."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any, AsyncGenerator

from dojoagents.agent.events import AgentEvent, AgentEventSink
from dojoagents.logging import get_logger

LOGGER = get_logger(__name__)


async def stream_persisted_run_events(
    service: Any,
    principal: Any,
    run_id: str,
    *,
    after_seq: int = 0,
    poll_seconds: float = 0.05,
) -> AsyncGenerator[dict[str, Any], None]:
    """Replay canonical events and follow a run without process-local truth."""

    sequence = max(0, int(after_seq))
    started_at = time.monotonic()
    last_wait_log_at = started_at
    last_status: str | None = None
    LOGGER.info(
        "Persisted run SSE started: run_id=%s after_seq=%d poll_seconds=%.3f",
        run_id,
        sequence,
        poll_seconds,
    )
    while True:
        page = await service.read_events(principal, run_id, after_seq=sequence, limit=200)
        if page.items:
            LOGGER.debug(
                "Persisted run SSE loaded events: run_id=%s count=%d first_sequence=%d last_sequence=%d",
                run_id,
                len(page.items),
                page.items[0].sequence,
                page.items[-1].sequence,
            )
        for event in page.items:
            sequence = event.sequence
            payload = dict(event.payload) if isinstance(event.payload, dict) else {"data": event.payload}
            yield {"sequence": event.sequence, "type": event.event_type, **payload}
        run = await service.get_run(principal, run_id)
        if run.status != last_status:
            LOGGER.info(
                "Persisted run SSE observed status: run_id=%s status=%s sequence=%d",
                run_id,
                run.status,
                sequence,
            )
            last_status = run.status
        if run.status != "running" and run.status != "cancellation_requested":
            trailing = await service.read_events(principal, run_id, after_seq=sequence, limit=200)
            if not trailing.items:
                LOGGER.info(
                    "Persisted run SSE completed: run_id=%s status=%s last_sequence=%d elapsed_seconds=%.3f",
                    run_id,
                    run.status,
                    sequence,
                    time.monotonic() - started_at,
                )
                return
            continue
        now = time.monotonic()
        if not page.items and now - last_wait_log_at >= 10:
            LOGGER.warning(
                "Persisted run SSE is waiting with no new events: run_id=%s status=%s after_seq=%d elapsed_seconds=%.3f",
                run_id,
                run.status,
                sequence,
                now - started_at,
            )
            last_wait_log_at = now
        await asyncio.sleep(poll_seconds)


def make_stream_delta_callback(queue: asyncio.Queue):
    """Backward-compatible callback that pushes raw text deltas onto a queue."""

    def callback(delta: str) -> None:
        try:
            loop = asyncio.get_running_loop()
            loop.call_soon_threadsafe(queue.put_nowait, delta)
        except RuntimeError:
            pass

    return callback


def make_event_queue_sink(
    queue: asyncio.Queue,
    *,
    run_id: str,
    session_id: str,
) -> AgentEventSink:
    """Create a request-scoped event sink that writes typed events to a queue."""

    def emit(event: AgentEvent) -> None:
        try:
            loop = asyncio.get_running_loop()
            loop.call_soon_threadsafe(queue.put_nowait, event.to_dict())
        except RuntimeError:
            pass

    return AgentEventSink(run_id=run_id, session_id=session_id, emit=emit)


def _make_chunk_line(
    completion_id: str,
    created: int,
    model: str,
    choice_delta: dict[str, Any],
    *,
    dojo_event: dict[str, Any] | None = None,
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
        dojo_event=dojo_event,
    )
    return chunk.to_sse_line()


def _tool_delta_from_event(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "tool_calls": [
            {
                "index": 0,
                "id": event["call_id"],
                "type": "function",
                "function": {
                    "name": event["tool"],
                    "arguments": json.dumps(event.get("arguments") or {}, ensure_ascii=False),
                },
            }
        ]
    }


async def stream_completion_chunks(
    queue: asyncio.Queue,
    *,
    model: str,
    event_format: str = "openai.v1",
    completion_id: str | None = None,
    created: int | None = None,
) -> AsyncGenerator[str, None]:
    """Drain event queue and emit OpenAI-compatible SSE lines with optional dojo events."""
    completion_id = completion_id or f"chatcmpl-dojo-{uuid.uuid4().hex[:8]}"
    created = created or int(time.time())
    dojo_v2 = event_format == "dojo.v2"

    yield _make_chunk_line(
        completion_id,
        created,
        model,
        {"delta": {"role": "assistant", "content": ""}, "finish_reason": None},
    )

    terminal_error: dict[str, Any] | None = None
    terminal_done: dict[str, Any] | None = None

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
            continue
        if not isinstance(item, dict):
            continue

        if "tool_calls" in item:
            yield _make_chunk_line(
                completion_id,
                created,
                model,
                {"delta": item, "finish_reason": None},
            )
            continue

        event_type = item.get("type")
        if event_type == "delta":
            yield _make_chunk_line(
                completion_id,
                created,
                model,
                {"delta": {"content": item.get("text", "")}, "finish_reason": None},
                dojo_event=item if dojo_v2 else None,
            )
            continue

        if event_type == "tool_start":
            yield _make_chunk_line(
                completion_id,
                created,
                model,
                {"delta": _tool_delta_from_event(item), "finish_reason": None},
                dojo_event=item if dojo_v2 else None,
            )
            continue

        if event_type == "done":
            terminal_done = item
            continue

        if event_type == "error":
            terminal_error = item
            continue

        if dojo_v2:
            yield _make_chunk_line(
                completion_id,
                created,
                model,
                {"delta": {}, "finish_reason": None},
                dojo_event=item,
            )

    finish_reason = "stop"
    dojo_event = None
    if dojo_v2:
        dojo_event = terminal_error or terminal_done

    yield _make_chunk_line(
        completion_id,
        created,
        model,
        {"delta": {}, "finish_reason": finish_reason},
        dojo_event=dojo_event,
    )

    from dojoagents.agent.models import ChatCompletionChunk

    yield ChatCompletionChunk.done_sentinel()
