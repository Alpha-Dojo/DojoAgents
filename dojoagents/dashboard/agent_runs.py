from __future__ import annotations

import asyncio
import concurrent.futures
import time
import uuid
from dataclasses import dataclass, field
import threading
from typing import Any, Literal

from dojoagents.agent.events import AgentEventSink
from dojoagents.agent.models import AgentResponse, ChatRequest

RunStatus = Literal["running", "done", "error", "cancelled"]

_RUN_TTL_SECONDS = 60 * 60


@dataclass
class AgentRunRecord:
    id: str
    session_id: str
    model: str
    status: RunStatus = "running"
    events: list[dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    task: concurrent.futures.Future[Any] | None = None

    def append_event(self, payload: dict[str, Any]) -> None:
        self.events.append(payload)
        self.updated_at = time.time()

    def set_status(self, status: RunStatus) -> None:
        self.status = status
        self.updated_at = time.time()

    async def wait_for_events(self, cursor: int, timeout: float = 0.25) -> tuple[int, RunStatus]:
        if cursor < len(self.events) or self.status != "running":
            return len(self.events), self.status
        await asyncio.sleep(timeout)
        return len(self.events), self.status


class AgentRunManager:
    def __init__(self) -> None:
        self._runs: dict[str, AgentRunRecord] = {}
        self._lock = asyncio.Lock()
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="dojo-agent-runs",
            daemon=True,
        )
        self._thread.start()

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def get(self, run_id: str) -> AgentRunRecord | None:
        return self._runs.get(run_id)

    async def create_run(
        self,
        *,
        request: ChatRequest,
        model: str,
        agent: Any,
        on_started: Any | None = None,
        on_completed: Any | None = None,
        on_failed: Any | None = None,
        on_cancelled: Any | None = None,
    ) -> AgentRunRecord:
        await self._prune_expired()
        run_id = f"run-{uuid.uuid4().hex[:8]}"
        record = AgentRunRecord(id=run_id, session_id=request.session_id, model=model)
        async with self._lock:
            self._runs[run_id] = record
        if on_started is not None:
            result = on_started(record)
            if asyncio.iscoroutine(result):
                await result

        def emit_event(event) -> None:
            payload = event.to_dict()
            record.append_event(payload)

        sink = AgentEventSink(run_id=run_id, session_id=request.session_id, emit=emit_event)

        async def _execute() -> None:
            try:
                response: AgentResponse = await agent.run(request, event_sink=sink)
                if not sink.events or sink.events[-1]["type"] not in {"done", "error"}:
                    tool_trace = response.metadata.get("tool_trace", [])
                    tool_steps = len(tool_trace) if isinstance(tool_trace, list) else 0
                    sink.done(model_id=model, tool_trace=tool_trace, tool_steps=tool_steps)
                record.set_status("done")
                if on_completed is not None:
                    result = on_completed(record, response)
                    if asyncio.iscoroutine(result):
                        await result
            except asyncio.CancelledError:
                if not sink.events or sink.events[-1]["type"] not in {"done", "error"}:
                    sink.error("Run cancelled", code="cancelled")
                record.set_status("cancelled")
                if on_cancelled is not None:
                    result = on_cancelled(record)
                    if asyncio.iscoroutine(result):
                        await result
                raise
            except Exception as exc:  # noqa: BLE001
                if not sink.events or sink.events[-1]["type"] not in {"done", "error"}:
                    sink.error(str(exc))
                record.set_status("error")
                if on_failed is not None:
                    result = on_failed(record, exc)
                    if asyncio.iscoroutine(result):
                        await result

        record.task = asyncio.run_coroutine_threadsafe(_execute(), self._loop)
        return record

    async def cancel_run(self, run_id: str) -> bool:
        record = self._runs.get(run_id)
        if record is None or record.status != "running" or record.task is None:
            return False
        record.task.cancel()
        try:
            await asyncio.wrap_future(record.task)
        except asyncio.CancelledError:
            pass
        except concurrent.futures.CancelledError:
            pass
        if record.status == "running":
            record.set_status("cancelled")
        return True

    async def _prune_expired(self) -> None:
        cutoff = time.time() - _RUN_TTL_SECONDS
        stale = [run_id for run_id, record in self._runs.items() if record.updated_at < cutoff]
        for run_id in stale:
            record = self._runs.pop(run_id, None)
            if record and record.task and not record.task.done():
                record.task.cancel()
