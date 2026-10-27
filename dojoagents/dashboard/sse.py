"""SSE streaming module for OpenAI-compatible chat completion chunks."""

from __future__ import annotations

import anyio
import json
import threading
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, AsyncGenerator

from dojoagents.agent.events import AgentEvent, AgentEventSink
from dojoagents.logging import get_logger

LOGGER = get_logger(__name__)

SSE_EVENT_BUFFER_SIZE = 32
SSE_PRODUCER_STOP_TIMEOUT_SECONDS = 5.0


class StreamBackpressureError(RuntimeError):
    """A synchronous event-loop producer exhausted its bounded stream."""


@dataclass(frozen=True)
class OwnedSSEProducer:
    """Handle for an app-owned producer that a response generator may cancel.

    The producer enters and exits its own cancel scope in one task.  The response
    generator only calls :meth:`stop`, so no cancel-scope context manager spans
    an ASGI ``yield`` or gets closed by Starlette's disconnect task.
    """

    cancel_scope: anyio.CancelScope
    done: anyio.Event
    name: str

    async def stop(self, *, timeout: float = SSE_PRODUCER_STOP_TIMEOUT_SECONDS) -> bool:
        """Cancel the producer and wait a bounded time for owned cleanup."""

        self.cancel_scope.cancel()
        with anyio.CancelScope(shield=True):
            with anyio.move_on_after(timeout) as timeout_scope:
                await self.done.wait()
        if timeout_scope.cancelled_caught:
            LOGGER.warning(
                "SSE producer did not stop within %.1fs: name=%s",
                timeout,
                self.name,
            )
            return False
        return True


async def start_owned_sse_producer(
    task_group: anyio.abc.TaskGroup,
    producer: Callable[[], Awaitable[None]],
    *,
    name: str,
) -> OwnedSSEProducer:
    """Start ``producer`` under an app-owned group and return its cancel handle."""

    async def _run(
        *,
        task_status: anyio.abc.TaskStatus[OwnedSSEProducer] = anyio.TASK_STATUS_IGNORED,
    ) -> None:
        done = anyio.Event()
        with anyio.CancelScope() as cancel_scope:
            task_status.started(OwnedSSEProducer(cancel_scope=cancel_scope, done=done, name=name))
            try:
                await producer()
            except anyio.get_cancelled_exc_class():
                raise
            except BaseExceptionGroup as exc:
                cancelled, remainder = exc.split(anyio.get_cancelled_exc_class())
                if cancelled is not None:
                    raise cancelled
                LOGGER.exception("Grouped failure in app-owned SSE producer '%s': %s", name, remainder or exc)
            except Exception:
                # App-level task groups must not be torn down by a single HTTP
                # stream. Endpoint producers translate expected failures into
                # their stream before this final defensive boundary.
                LOGGER.exception("Failure in app-owned SSE producer '%s'", name)
            finally:
                done.set()

    return await task_group.start(_run, name=name)


class SSEEventStream:
    """Bounded request stream with a safe synchronous callback boundary.

    Callbacks running on the request's event-loop thread cannot block without
    deadlocking the consumer, so they use ``send_nowait`` and fail closed when
    the explicit buffer is exhausted. External threads use a BlockingPortal
    and therefore apply real blocking backpressure.
    """

    def __init__(self, max_buffer_size: int = SSE_EVENT_BUFFER_SIZE) -> None:
        if max_buffer_size <= 0:
            raise ValueError("SSE event buffer size must be positive")
        self.max_buffer_size = max_buffer_size
        self.send_stream, self.receive_stream = anyio.create_memory_object_stream[Any](
            max_buffer_size=max_buffer_size
        )
        self._portal: anyio.from_thread.BlockingPortal | None = None
        self._owner_thread_id: int | None = None
        self._closed = False
        self._state_lock = threading.Lock()

    def bind_portal(self, portal: anyio.from_thread.BlockingPortal) -> None:
        with self._state_lock:
            self._portal = portal
            self._owner_thread_id = threading.get_ident()

    def unbind_portal(self) -> None:
        with self._state_lock:
            self._portal = None
            self._owner_thread_id = None

    def publish_sync(self, item: Any) -> None:
        with self._state_lock:
            if self._closed:
                return
            portal = self._portal
            owner_thread_id = self._owner_thread_id
        try:
            if owner_thread_id == threading.get_ident():
                self.send_stream.send_nowait(item)
            elif portal is not None:
                portal.call(self.send_stream.send, item)
            else:
                raise RuntimeError("SSE event stream is not active")
        except anyio.WouldBlock as exc:
            raise StreamBackpressureError(
                f"SSE event buffer is full (capacity={self.max_buffer_size})"
            ) from exc
        except (anyio.BrokenResourceError, anyio.ClosedResourceError, RuntimeError):
            # Browser disconnect/portal shutdown may race with a late provider
            # callback. The request owner has already cancelled the producer.
            with self._state_lock:
                if self._closed or self._portal is None:
                    return
            raise

    async def send(self, item: Any) -> None:
        with self._state_lock:
            if self._closed:
                return
        await self.send_stream.send(item)

    async def close(self) -> None:
        with self._state_lock:
            if self._closed:
                return
            self._closed = True
        await self.send_stream.aclose()


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
        await anyio.sleep(poll_seconds)


def make_stream_delta_callback(stream: SSEEventStream):
    """Create a sync callback backed by a bounded request stream."""

    def callback(delta: str) -> None:
        stream.publish_sync(delta)

    return callback


def make_event_queue_sink(
    stream: SSEEventStream,
    *,
    run_id: str,
    session_id: str,
) -> AgentEventSink:
    """Create a request-scoped event sink that writes to a bounded stream."""

    def emit(event: AgentEvent) -> None:
        stream.publish_sync(event.to_dict())

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
    receive_stream: anyio.abc.ObjectReceiveStream[Any],
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

    async for item in receive_stream:
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
