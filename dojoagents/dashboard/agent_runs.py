from __future__ import annotations

import anyio
import concurrent.futures
import inspect
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from dojoagents.agent.events import AgentEventSink
from dojoagents.agent.models import AgentResponse, ChatRequest
from dojoagents.config.models import LLMProviderConfig
from dojoagents.logging import get_logger
from dojoagents.utils.blocking_portal import ThreadedBlockingPortal

LOGGER = get_logger(__name__)

RunStatus = Literal["running", "done", "error", "cancelled"]

_RUN_TTL_SECONDS = 60 * 60
# Cancellation is not instantaneous: the agent has to unwind its own awaits and
# anyio has to hand the cancellation back to the run's event loop.  The wait is
# bounded so a wedged run can never pin the HTTP handler.
_RUN_CANCEL_SETTLE_SECONDS = 10.0


class UnsupportedInputModalityError(ValueError):
    """The selected model cannot consume one or more request modalities."""


class PortalShutdownError(RuntimeError):
    """A background run was requested after the run manager stopped accepting work."""


def _log_unobserved_run_failure(task: concurrent.futures.Future[Any]) -> None:
    """Surface a run task that failed outside the normal error/cancel handling."""

    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None and not isinstance(exc, Exception):
        LOGGER.error("Dashboard background run task aborted: %r", exc)


def _content_input_modalities(content: Any) -> set[str]:
    if content is None:
        return set()
    if isinstance(content, str):
        return {"text"} if content.strip() else set()
    if not isinstance(content, list):
        return {"text"} if str(content).strip() else set()
    modalities: set[str] = set()
    for part in content:
        if not isinstance(part, dict):
            continue
        part_type = str(part.get("type") or "").strip().lower()
        if part_type == "text" and str(part.get("text") or "").strip():
            modalities.add("text")
            continue
        if part_type == "image_url":
            image_url = part.get("image_url")
            url = image_url.get("url") if isinstance(image_url, dict) else None
            if str(url or "").strip():
                modalities.add("image")
    return modalities


def _request_input_modalities(request: ChatRequest) -> set[str]:
    modalities = _content_input_modalities(request.message)
    metadata = request.metadata if isinstance(request.metadata, dict) else {}
    modalities.update(_content_input_modalities(request.runtime_content))
    modalities.update(_content_input_modalities(metadata.get("user_content")))
    history = metadata.get("history")
    if isinstance(history, list):
        for message in history:
            if not isinstance(message, dict):
                continue
            modalities.update(_content_input_modalities(message.get("content")))
    return modalities


@dataclass
class AgentRunRecord:
    id: str
    session_id: str
    model: str
    owner_tenant_id: str = ""
    owner_user_id: str = ""
    status: RunStatus = "running"
    events: list[dict[str, Any]] = field(default_factory=list)
    result_metadata: dict[str, Any] = field(default_factory=dict)
    result_content: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    # Handle to the run task living on the manager's portal loop.  It is a
    # thread-safe ``concurrent.futures.Future`` rather than a bare loop task, so
    # the manager never needs the asyncio module for lifecycle control.
    task: concurrent.futures.Future[Any] | None = None
    _settled: threading.Event = field(default_factory=threading.Event, repr=False, compare=False)

    @property
    def settled(self) -> bool:
        """Whether the run task has finished unwinding (any status)."""

        return self._settled.is_set()

    def mark_settled(self) -> None:
        self._settled.set()

    def wait_settled(self, timeout: float) -> bool:
        """Block the current thread until the run unwinds. Used by cancel/status paths."""

        return self._settled.wait(timeout)

    def is_visible_to(self, principal: Any) -> bool:
        if not self.owner_user_id:
            return True
        return self.owner_user_id == str(getattr(principal, "user_id", "") or "") and self.owner_tenant_id == str(getattr(principal, "tenant_id", "") or "")

    def append_event(self, payload: dict[str, Any]) -> None:
        self.events.append(payload)
        self.updated_at = time.time()

    def set_status(self, status: RunStatus) -> None:
        self.status = status
        self.updated_at = time.time()

    def set_result(self, response: AgentResponse) -> None:
        self.result_content = str(response.content or "")
        metadata = response.metadata
        self.result_metadata = dict(metadata) if isinstance(metadata, dict) else {}

    def set_error_result(self, exc: BaseException) -> None:
        self.result_content = str(exc)
        self.result_metadata = {"error": "runtime_error", "message": str(exc)}

    def to_status_dict(self) -> dict[str, Any]:
        metadata = dict(self.result_metadata) if isinstance(self.result_metadata, dict) else {}
        return {
            "run_id": self.id,
            "session_id": self.session_id,
            "status": self.status,
            "event_count": len(self.events),
            "model": self.model,
            "metadata": metadata,
            "pipeline_completed": metadata.get("pipeline_completed"),
            "content": self.result_content,
        }

    async def wait_for_events(self, cursor: int, timeout: float = 0.25) -> tuple[int, RunStatus]:
        if cursor < len(self.events) or self.status != "running":
            return len(self.events), self.status
        await anyio.sleep(timeout)
        return len(self.events), self.status


async def validate_request_modalities(request: ChatRequest, agent: Any) -> None:
    requested = _request_input_modalities(request)
    if not requested:
        return
    provider_cfg = getattr(agent, "provider_config", None)
    registry = getattr(agent, "model_context_registry", None)
    if not isinstance(provider_cfg, LLMProviderConfig) or registry is None:
        return
    provider_name = getattr(getattr(agent, "llm_provider", None), "name", "openai")
    if not isinstance(provider_name, str) or not provider_name:
        provider_name = "openai"
    info = await registry.resolve_info(provider_name, provider_cfg)
    supported = {str(modality).strip().lower() for modality in info.input_modalities if str(modality).strip()}
    if not supported:
        return
    unsupported = sorted(modality for modality in requested if modality not in supported)
    if not unsupported:
        return
    model_label = provider_cfg.model or "unknown"
    if provider_cfg.author:
        model_label = f"{provider_cfg.author}/{model_label}"
    raise UnsupportedInputModalityError(
        f"Model '{model_label}' does not support input modalities: {', '.join(unsupported)}. " f"Supported input modalities: {', '.join(sorted(supported))}."
    )


class AgentRunManager:
    """Owns Dashboard background runs and the portal loop they execute on.

    Runs must outlive the HTTP request that created them, so they execute on a
    dedicated event loop owned by this component.  The portal is started once
    here and closed by :meth:`shutdown`; it is never created per request, and no
    code path keeps a second, older loop alive alongside it.
    """

    def __init__(self, *, portal: ThreadedBlockingPortal | None = None) -> None:
        self._runs: dict[str, AgentRunRecord] = {}
        self._lock = anyio.Lock()
        self._portal = portal or ThreadedBlockingPortal(name="dojo-agent-runs")
        self._portal.start()
        self._closed = False

    def get(self, run_id: str) -> AgentRunRecord | None:
        return self._runs.get(run_id)

    async def shutdown(self, *, timeout: float = 10.0) -> None:
        """Cancel every live run, then close the portal and join its thread.

        Idempotent: the Dashboard lifespan calls this on teardown, and a second
        call (or a call after a failed start) is a no-op.
        """

        if self._closed:
            return
        self._closed = True
        for record in list(self._runs.values()):
            if record.task is not None and not record.task.done():
                await self._portal.run_sync(record.task.cancel, abandon_on_cancel=True)
        for record in list(self._runs.values()):
            if record.task is not None:
                await self._portal.run_sync(
                    record.wait_settled,
                    timeout,
                    abandon_on_cancel=True,
                )
        await self._portal.ashutdown(timeout=timeout)

    async def create_run(
        self,
        *,
        request: ChatRequest,
        model: str,
        agent: Any,
        runtime: Any | None = None,
        on_started: Any | None = None,
        on_completed: Any | None = None,
        on_failed: Any | None = None,
        on_cancelled: Any | None = None,
    ) -> AgentRunRecord:
        await self._prune_expired()
        await validate_request_modalities(request, agent)
        run_id = f"run-{uuid.uuid4().hex[:8]}"
        principal = request.principal
        record = AgentRunRecord(
            id=run_id,
            session_id=request.session_id,
            model=model,
            owner_tenant_id=str(getattr(principal, "tenant_id", "") or ""),
            owner_user_id=str(getattr(principal, "user_id", "") or ""),
        )
        async with self._lock:
            self._runs[run_id] = record
        if on_started is not None:
            result = on_started(record)
            if inspect.isawaitable(result):
                await result

        def emit_event(event) -> None:
            payload = event.to_dict()
            record.append_event(payload)

        sink = AgentEventSink(run_id=run_id, session_id=request.session_id, emit=emit_event)

        async def _execute() -> None:
            try:
                if runtime is not None:
                    from dojoagents.tasks.runtime_helpers import run_agent_with_tasks

                    response: AgentResponse = await run_agent_with_tasks(
                        runtime,
                        request,
                        run_agent=agent.run,
                        event_sink=sink,
                    )
                else:
                    response = await agent.run(request, event_sink=sink)
                if not sink.events or sink.events[-1]["type"] not in {"done", "error"}:
                    tool_trace = response.metadata.get("tool_trace", [])
                    tool_steps = len(tool_trace) if isinstance(tool_trace, list) else 0
                    sink.done(model_id=model, tool_trace=tool_trace, tool_steps=tool_steps)
                record.set_result(response)
                record.set_status("done")
                if on_completed is not None:
                    result = on_completed(record, response)
                    if inspect.isawaitable(result):
                        await result
                LOGGER.info(
                    "Dashboard background run completed: run_id=%s event_count=%d content_length=%d",
                    run_id,
                    len(record.events),
                    len(record.result_content),
                )
            except anyio.get_cancelled_exc_class():
                if not sink.events or sink.events[-1]["type"] not in {"done", "error"}:
                    sink.error("Run cancelled", code="cancelled")
                record.result_metadata = {"cancelled": True}
                record.set_status("cancelled")
                if on_cancelled is not None:
                    result = on_cancelled(record)
                    if inspect.isawaitable(result):
                        await result
                LOGGER.info(
                    "Dashboard background run cancelled: run_id=%s event_count=%d",
                    run_id,
                    len(record.events),
                )
                raise
            except Exception as exc:  # noqa: BLE001
                if not sink.events or sink.events[-1]["type"] not in {"done", "error"}:
                    sink.error(str(exc))
                record.set_error_result(exc)
                record.set_status("error")
                if on_failed is not None:
                    result = on_failed(record, exc)
                    if inspect.isawaitable(result):
                        await result
                LOGGER.exception(
                    "Dashboard background run failed: run_id=%s status=%s event_count=%d",
                    run_id,
                    record.status,
                    len(record.events),
                )
            finally:
                # Signals cancel/status callers that the run has fully unwound,
                # including the receipt of the cancellation itself.
                record.mark_settled()

        if self._closed:
            raise PortalShutdownError("the Dashboard run manager is shutting down and no longer accepts new runs")
        record.task = self._portal.start_task(_execute, name=f"dojo-run:{run_id}")
        record.task.add_done_callback(_log_unobserved_run_failure)
        LOGGER.info(
            "Dashboard background run scheduled: run_id=%s session_id=%s model=%s canonical_session=%s",
            run_id,
            request.session_id,
            model,
            bool(getattr(agent, "session_service", None)),
        )
        return record

    async def cancel_run(self, run_id: str) -> bool:
        record = self._runs.get(run_id)
        if record is None or record.status != "running" or record.task is None:
            return False
        # Off the event loop: cancelling the future hands the cancellation back to
        # the portal loop, which blocks until that loop services it.
        await self._portal.run_sync(record.task.cancel, abandon_on_cancel=True)
        # The run's own cancellation handler sets the final status, so wait for it
        # to unwind instead of guessing here.  The wait is bounded and runs on a
        # worker thread because the run lives on the portal loop, not this one.
        await self._portal.run_sync(
            record.wait_settled,
            _RUN_CANCEL_SETTLE_SECONDS,
            abandon_on_cancel=True,
        )
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
