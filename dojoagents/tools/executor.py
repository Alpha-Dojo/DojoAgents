from __future__ import annotations

import asyncio
import time
from typing import Any
from dojoagents.agent.models import ToolCall, ToolResult, ToolResultList
from dojoagents.tools.escalation import AgentEscalationError, escalation_metadata
from dojoagents.tools.artifacts import (
    ARTIFACT_PERSIST_THRESHOLD_CHARS,
    ARTIFACT_KEEP_FULL_CONTENT_TOOLS,
    ToolResultArtifactAdapter,
    ToolResultArtifactStore,
    build_artifact_pointer_message,
)
from dojoagents.tools.registry import ToolRegistry
from dojoagents.tools.sandbox import SandboxPolicy
from dojoagents.tools.terminal_tool import truncate_output
from dojoagents.logging import LOGGER

_MAX_TOOL_RESULT_CHARS = 30000


class ToolExecutor:
    def __init__(
        self,
        registry: ToolRegistry,
        sandbox: SandboxPolicy,
        *,
        artifact_store: ToolResultArtifactStore | None = None,
        artifact_adapter: ToolResultArtifactAdapter | None = None,
        presenter_registry: Any = None,
    ) -> None:
        self.registry = registry
        self.sandbox = sandbox
        self.presenters = presenter_registry
        self.artifact_store = artifact_store
        self.artifact_adapter = artifact_adapter

    async def execute_many(self, tool_calls: list[ToolCall], *, session_id: str = "") -> ToolResultList:
        results = ToolResultList()
        if not tool_calls:
            return results

        tasks = [self.execute_one(call, session_id=session_id) for call in tool_calls]
        executed_results = await asyncio.gather(*tasks)
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
        try:
            self.sandbox.check_tool(call.name)
            raw = await asyncio.wait_for(
                spec.handler(dict(call.arguments)),
                timeout=self.sandbox.timeout_seconds,
            )
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            return self._coerce_result(call, raw, session_id=session_id, latency_ms=latency_ms)
        except AgentEscalationError as exc:
            LOGGER.info(
                "Tool '%s' escalated to user input (call_id: %s, code: %s)",
                call.name,
                call.id,
                exc.code,
            )
            return ToolResult(
                call_id=call.id,
                name=call.name,
                ok=False,
                error=exc.message,
                latency_ms=int((time.perf_counter() - started_at) * 1000),
                metadata=escalation_metadata(exc, source_tool=call.name),
            )
        except Exception as exc:
            LOGGER.exception(f"Error executing tool '{call.name}' (call_id: {call.id})")
            return ToolResult(
                call_id=call.id,
                name=call.name,
                ok=False,
                error=str(exc),
            )
        finally:
            active_session_id.reset(token)

    def _coerce_result(
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

        content = str(normalized.get("content", ""))
        if len(content) > _MAX_TOOL_RESULT_CHARS:
            content = truncate_output(content, _MAX_TOOL_RESULT_CHARS)
            normalized["truncated"] = True
        metadata = dict(normalized.get("metadata", {}))
        metadata.setdefault("tool_arguments", dict(call.arguments))
        if session_id:
            metadata.setdefault("session_id", session_id)

        exit_code = metadata.get("exit_code")
        ok = True
        error = str(normalized.get("error") or "").strip()
        if exit_code is not None:
            try:
                exit_code_int = int(exit_code)
            except (TypeError, ValueError):
                exit_code_int = 0
            if exit_code_int != 0:
                ok = False
                if not error:
                    error = content.strip() or f"Process exited with code {exit_code_int}"

        artifact_path = None
        persist_artifact = self.artifact_store is not None and session_id and len(content) >= ARTIFACT_PERSIST_THRESHOLD_CHARS
        if persist_artifact:
            try:
                artifact_data = normalized.get("data")
                if self.artifact_adapter is not None:
                    artifact_data = self.artifact_adapter.extract_data(
                        call.name,
                        content,
                        artifact_data,
                    )
                artifact_path = self.artifact_store.save(
                    session_id=session_id,
                    call_id=call.id,
                    tool_name=call.name,
                    arguments=dict(call.arguments),
                    content=content,
                    data=artifact_data,
                    ok=True,
                    truncated=bool(normalized.get("truncated", False)),
                )
                metadata["artifact_path"] = str(artifact_path)
                metadata["artifact_call_id"] = call.id
                if call.name not in ARTIFACT_KEEP_FULL_CONTENT_TOOLS:
                    pointer_builder = self.artifact_adapter.build_pointer if self.artifact_adapter is not None else build_artifact_pointer_message
                    content = pointer_builder(
                        tool_name=call.name,
                        call_id=call.id,
                        arguments=dict(call.arguments),
                        data=normalized.get("data"),
                        content=content,
                    )
            except Exception:
                LOGGER.exception(
                    "Failed to persist tool result artifact: session_id=%s call_id=%s tool=%s",
                    session_id,
                    call.id,
                    call.name,
                )
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
