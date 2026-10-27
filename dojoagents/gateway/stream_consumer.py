from __future__ import annotations

import anyio
import re
import threading
import time
from typing import Any

from dojoagents.logging import LOGGER


class GatewayStreamConsumer:
    """Async consumer that accumulates streamed tokens, suppresses thinking/reasoning tags,
    and throttles progressive platform message edits.
    """

    def __init__(
        self,
        adapter: Any,
        target: str,
        thread_id: str | None = None,
        edit_interval: float = 0.2,
    ) -> None:
        self.adapter = adapter
        self.target = target
        self.thread_id = thread_id
        self.edit_interval = edit_interval
        
        self._send_stream: anyio.abc.ObjectSendStream[str] | None = None
        self._receive_stream: anyio.abc.ObjectReceiveStream[str] | None = None
        self.accumulated = ""
        self.message_id: str | None = None
        
        self._stop_event = anyio.Event()
        self._done_event = anyio.Event()
        self._error: Exception | None = None
        self._portal: anyio.from_thread.BlockingPortal | None = None
        self._owner_thread_id: int | None = None
        self._closed = True
        self._state_lock = threading.Lock()

    def on_delta(self, token: str) -> None:
        """Publish a token with bounded same-loop or cross-thread backpressure."""
        with self._state_lock:
            if self._closed:
                return
            send_stream = self._send_stream
            portal = self._portal
            owner_thread_id = self._owner_thread_id
        if send_stream is None:
            return
        try:
            if owner_thread_id == threading.get_ident():
                send_stream.send_nowait(token)
            elif portal is not None:
                portal.call(send_stream.send, token)
            else:
                raise RuntimeError("gateway stream consumer is not active")
        except anyio.WouldBlock as exc:
            raise RuntimeError("gateway delta stream buffer is full (capacity=64)") from exc
        except (anyio.BrokenResourceError, anyio.ClosedResourceError, RuntimeError):
            with self._state_lock:
                if self._closed or self._portal is None:
                    return
            raise

    async def start(self, task_group: anyio.abc.TaskGroup) -> None:
        """Start the background consumer task."""
        self._stop_event = anyio.Event()
        self._done_event = anyio.Event()
        self._error = None
        self._send_stream, self._receive_stream = anyio.create_memory_object_stream[str](
            max_buffer_size=64
        )
        self._portal = anyio.from_thread.BlockingPortal()
        await self._portal.__aenter__()
        self._owner_thread_id = threading.get_ident()
        with self._state_lock:
            self._closed = False
        task_group.start_soon(self._run_owned)

    async def stop(self) -> None:
        """Signal the consumer to stop and wait for it to process remaining queue items."""
        with self._state_lock:
            already_closed = self._closed
            self._closed = True
            send_stream = self._send_stream
        if already_closed:
            await self._done_event.wait()
            return
        self._stop_event.set()
        if send_stream is not None:
            await send_stream.aclose()
        await self._done_event.wait()
        if self._error is not None:
            LOGGER.error("Gateway stream consumer stopped after an error: %s", self._error)
        portal = self._portal
        self._portal = None
        self._owner_thread_id = None
        if portal is not None:
            await portal.__aexit__(None, None, None)

    async def _run_owned(self) -> None:
        try:
            await self._run()
        except anyio.get_cancelled_exc_class():
            raise
        except Exception as exc:
            self._error = exc
        finally:
            self._done_event.set()

    async def _run(self) -> None:
        receive_stream = self._receive_stream
        if receive_stream is None:
            raise RuntimeError("gateway stream consumer was not started")
        last_edit_time = 0.0
        async with receive_stream:
            async for token in receive_stream:
                if token:
                    self.accumulated += token
                now = time.time()
                if now - last_edit_time >= self.edit_interval:
                    await self._flush()
                    last_edit_time = now

        # Final flush to ensure all tokens are delivered
        await self._flush()

    async def _flush(self) -> None:
        display_text = self._strip_thinking(self.accumulated)
        if not display_text:
            return

        if self.message_id is None:
            # First send
            result = await self.adapter.send(
                self.target,
                display_text,
                thread_id=self.thread_id,
            )
            if result.success:
                self.message_id = result.message_id
        else:
            # Edit existing message
            edit_fn = getattr(self.adapter, "edit", None)
            if edit_fn is not None:
                await edit_fn(
                    self.target,
                    self.message_id,
                    display_text,
                    thread_id=self.thread_id,
                )

    def _strip_thinking(self, text: str) -> str:
        """Remove open/closed thought/thinking/reasoning blocks."""
        # Strip complete blocks
        cleaned = re.sub(r"<(think|thought|reasoning)>.*?</\1>", "", text, flags=re.DOTALL)
        # Strip unclosed blocks at the end of the stream
        cleaned = re.sub(r"<(think|thought|reasoning)>.*", "", cleaned, flags=re.DOTALL)
        return cleaned
