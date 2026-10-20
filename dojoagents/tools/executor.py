from __future__ import annotations

import anyio
import time
from typing import Any
from dojoagents.agent.models import ToolCall, ToolResult, ToolResultList
from dojoagents.tools.escalation import AgentEscalationError, escalation_metadata
from dojoagents.tools.artifacts import (
    ARTIFACT_PERSIST_THRESHOLD_CHARS,
    ARTIFACT_KEEP_FULL_CONTENT_TOOLS,
    structured_artifact_data,
    ToolResultArtifactAdapter,
    ToolResultArtifactStore,
    build_artifact_pointer_message,
)
from dojoagents.sessions.atomic import FileStoreSizeError
from dojoagents.tools.registry import ToolRegistry
from dojoagents.tools.sandbox import SandboxPolicy
from dojoagents.tools.terminal_tool import truncate_output
from dojoagents.agent.telemetry import ToolCallEvent, current_run_id, emit
from dojoagents.tools.timing import collect_tool_timing
from dojoagents.logging import LOGGER
from dojoagents.utils.async_runtime import SyncWorkload, gather_ordered, run_sync_bounded

_MAX_TOOL_RESULT_CHARS = 30000


def _emit_tool_event(
    call: ToolCall,
    *,
    ok: bool,
    latency_ms: int,
    timing: Any,
    handler_ms: int = 0,
    postprocess_ms: int = 0,
) -> None:
    """Publish one neutral tool event. The host owns persistence."""
    emit(
        ToolCallEvent(
            run_id=current_run_id(),
            tool_name=call.name,
            call_id=call.id,
            latency_ms=latency_ms,
            ok=ok,
            timing=timing.snapshot(handler_ms=handler_ms, postprocess_ms=postprocess_ms) if timing else None,
        )
    )


class ToolExecutor:
    def __init__(
        self,
        registry: ToolRegistry,
        sandbox: SandboxPolicy,
        *,
        artifact_store: ToolResultArtifactStore | None = None,
        artifact_adapter: ToolResultArtifactAdapter | None = None,
        presenter_registry: Any = None,
        pointer_tools: tuple[str, ...] | frozenset[str] = (),
    ) -> None:
        self.registry = registry
        self.sandbox = sandbox
        self.presenters = presenter_registry
        self.artifact_store = artifact_store
        self.artifact_adapter = artifact_adapter
        self.pointer_tools = frozenset(pointer_tools)

    async def execute_many(self, tool_calls: list[ToolCall], *, session_id: str = "") -> ToolResultList:
        results = ToolResultList()
        if not tool_calls:
            return results

        executed_results = await gather_ordered(
            [lambda call=call: self.execute_one(call, session_id=session_id) for call in tool_calls]
        )
        for res in executed_results:
            results.append(res)
        return results

    async def execute(self, call: ToolCall, *, session_id: str = "") -> ToolResult:
        return await self.execute_one(call, session_id=session_id)

    async def execute_one(self, call: ToolCall, *, session_id: str = "") -> ToolResult:
        spec = self.registry.get(call.name)
        if spec is None:
            LOGGER.error(f"Tool '{call.name}' is not registered")
            return ToolResult(
                call_id=call.id,
                name=call.name,
                ok=False,
                error=f"Tool '{call.name}' is not registered",
            )
        from dojoagents.tools.process_registry import active_session_id

        token = active_session_id.set(session_id)
        started_at = time.perf_counter()
        with collect_tool_timing() as timing:
            try:
                with timing.span("sandbox_check", "guard"):
                    self.sandbox.check_tool(call.name)
                handler_started = time.perf_counter()
                with timing.span("handler", "handler"):
                    with anyio.fail_after(self.sandbox.timeout_seconds):
                        raw = await spec.handler(dict(call.arguments))
                handler_ms = int((time.perf_counter() - handler_started) * 1000)
                latency_ms = int((time.perf_counter() - started_at) * 1000)
                postprocess_started = time.perf_counter()
                result = await self._coerce_result(call, raw, session_id=session_id, latency_ms=latency_ms)
                _emit_tool_event(
                    call,
                    ok=True,
                    latency_ms=latency_ms,
                    timing=timing,
                    handler_ms=handler_ms,
                    postprocess_ms=int((time.perf_counter() - postprocess_started) * 1000),
                )
                return result
            except AgentEscalationError as exc:
                LOGGER.info(
                    "Tool '%s' escalated to user input (call_id: %s, code: %s)",
                    call.name,
                    call.id,
                    exc.code,
                )
                latency_ms = int((time.perf_counter() - started_at) * 1000)
                _emit_tool_event(call, ok=False, latency_ms=latency_ms, timing=timing)
                return ToolResult(
                    call_id=call.id,
                    name=call.name,
                    ok=False,
                    error=exc.message,
                    latency_ms=latency_ms,
                    metadata=escalation_metadata(exc, source_tool=call.name),
                )
            except TimeoutError:
                timeout_seconds = self.sandbox.timeout_seconds
                LOGGER.warning(
                    "Tool '%s' timed out after %ss (call_id: %s)",
                    call.name,
                    timeout_seconds,
                    call.id,
                )
                latency_ms = int((time.perf_counter() - started_at) * 1000)
                _emit_tool_event(call, ok=False, latency_ms=latency_ms, timing=timing)
                return ToolResult(
                    call_id=call.id,
                    name=call.name,
                    ok=False,
                    error=f"Tool '{call.name}' timed out after {timeout_seconds:g} seconds",
                    latency_ms=latency_ms,
                )
            except BaseExceptionGroup as exc:
                cancelled, remainder = exc.split(anyio.get_cancelled_exc_class())
                if cancelled is not None:
                    raise cancelled
                LOGGER.exception("Grouped error executing tool '%s' (call_id: %s)", call.name, call.id)
                latency_ms = int((time.perf_counter() - started_at) * 1000)
                _emit_tool_event(call, ok=False, latency_ms=latency_ms, timing=timing)
                return ToolResult(
                    call_id=call.id,
                    name=call.name,
                    ok=False,
                    error=str(remainder or exc),
                    latency_ms=latency_ms,
                )
            except Exception as exc:
                LOGGER.exception(f"Error executing tool '{call.name}' (call_id: {call.id})")
                latency_ms = int((time.perf_counter() - started_at) * 1000)
                _emit_tool_event(call, ok=False, latency_ms=latency_ms, timing=timing)
                return ToolResult(
                    call_id=call.id,
                    name=call.name,
                    ok=False,
                    error=str(exc),
                    latency_ms=latency_ms,
                )
            finally:
                active_session_id.reset(token)

    async def _coerce_result(
        self,
        call: ToolCall,
        raw: dict[str, Any] | str | None,
        *,
        session_id: str,
        latency_ms: int = 0,
    ) -> ToolResult:
        if raw is None:
            normalized: dict[str, Any] = {}
        elif isinstance(raw, str):
            normalized = {"content": raw}
        else:
            normalized = dict(raw)

        normalized.setdefault("content", "")
        normalized.setdefault("metadata", {})
        normalized["arguments"] = dict(call.arguments)
        normalized.setdefault("viz_blocks", [])
        normalized.setdefault("artifacts", [])
        normalized.setdefault("resource_changes", [])
        if self.presenters is not None:
            normalized = self.presenters.normalize(call.name, normalized)

        original_content = str(normalized.get("content", ""))
        source_truncated = bool(normalized.get("truncated", False))
        content = original_content
        if len(content) > _MAX_TOOL_RESULT_CHARS:
            content = truncate_output(content, _MAX_TOOL_RESULT_CHARS)
            normalized["truncated"] = True
        metadata = dict(normalized.get("metadata", {}))
        metadata.setdefault("tool_arguments", dict(call.arguments))
        if session_id:
            metadata.setdefault("session_id", session_id)

        exit_code = metadata.get("exit_code")
        declared_ok = normalized.get("ok", metadata.get("ok"))
        ok = bool(declared_ok) if declared_ok is not None else True
        error = str(normalized.get("error") or "").strip()
        if not ok and not error:
            error = content.strip() or f"Tool '{call.name}' failed"
        if exit_code is not None:
            try:
                exit_code_int = int(exit_code)
            except (TypeError, ValueError):
                exit_code_int = 0
            if exit_code_int != 0:
                ok = False
                if not error:
                    error = content.strip() or f"Process exited with code {exit_code_int}"

        persist_artifact = (
            self.artifact_store is not None
            and bool(session_id)
            and len(original_content) >= ARTIFACT_PERSIST_THRESHOLD_CHARS
        )
        if persist_artifact:
            try:
                artifact_data = normalized.get("data")
                if self.artifact_adapter is not None:
                    artifact_data = await run_sync_bounded(
                        self.artifact_adapter.extract_data,
                        call.name,
                        original_content,
                        artifact_data,
                        workload=SyncWorkload.CPU,
                    )
                artifact_path = await run_sync_bounded(
                    self.artifact_store.save,
                    session_id=session_id,
                    call_id=call.id,
                    tool_name=call.name,
                    arguments=dict(call.arguments),
                    content=original_content,
                    data=artifact_data,
                    ok=ok,
                    truncated=source_truncated,
                    error=error,
                )
            except FileStoreSizeError:
                raise
            except Exception:
                LOGGER.exception("Failed to persist tool result artifact: session_id=%s call_id=%s tool=%s", session_id, call.id, call.name)
            else:
                metadata["artifact_path"] = str(artifact_path)
                metadata["artifact_call_id"] = call.id
                if ok and call.name in self.pointer_tools and call.name not in ARTIFACT_KEEP_FULL_CONTENT_TOOLS:
                    source = await run_sync_bounded(
                        structured_artifact_data,
                        artifact_data,
                        original_content,
                        workload=SyncWorkload.CPU,
                    )
                    if source is not None:
                        try:
                            pointer_builder = self.artifact_adapter.build_pointer if self.artifact_adapter is not None else build_artifact_pointer_message
                            content = await run_sync_bounded(
                                pointer_builder,
                                tool_name=call.name,
                                call_id=call.id,
                                arguments=dict(call.arguments),
                                data=source,
                                content=original_content,
                                workload=SyncWorkload.CPU,
                            )
                            normalized["truncated"] = source_truncated
                        except Exception:
                            LOGGER.exception("Failed to build tool result artifact preview: call_id=%s tool=%s", call.id, call.name)
        return ToolResult(
            call_id=call.id,
            name=call.name,
            ok=ok,
            content=content,
            error=error,
            latency_ms=latency_ms,
            truncated=bool(normalized.get("truncated", False)),
            data=normalized.get("data"),
            viz_blocks=list(normalized.get("viz_blocks", [])),
            artifacts=list(normalized.get("artifacts", [])),
            resource_changes=list(normalized.get("resource_changes", [])),
            metadata=metadata,
        )
