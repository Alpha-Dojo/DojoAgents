from __future__ import annotations

import asyncio
import re
import time
from typing import Any


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
        
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.accumulated = ""
        self.message_id: str | None = None
        
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None
        self.loop = asyncio.get_running_loop()

    def on_delta(self, token: str) -> None:
        """Callback to receive token deltas. Thread-safe wrapper via loop scheduling or direct put."""
        try:
            current_loop = asyncio.get_running_loop()
            if current_loop is self.loop:
                self.queue.put_nowait(token)
            else:
                self.loop.call_soon_threadsafe(self.queue.put_nowait, token)
        except RuntimeError:
            self.loop.call_soon_threadsafe(self.queue.put_nowait, token)

    async def start(self) -> None:
        """Start the background consumer task."""
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Signal the consumer to stop and wait for it to process remaining queue items."""
        self._stop_event.set()
        # Put sentinel token to wake up queue get
        self.on_delta("")
        if self._task:
            await self._task

    async def _run(self) -> None:
        last_edit_time = 0.0
        while not self._stop_event.is_set() or not self.queue.empty():
            try:
                # Wait for token with timeout to ensure we flush periodically
                token = await asyncio.wait_for(self.queue.get(), timeout=self.edit_interval)
                if token:
                    self.accumulated += token
            except asyncio.TimeoutError:
                pass

            now = time.time()
            elapsed = now - last_edit_time
            if elapsed >= self.edit_interval or (self._stop_event.is_set() and self.queue.empty()):
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
