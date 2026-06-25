from __future__ import annotations

import asyncio
import time
from typing import Any
from dojoagents.agent.presenters import ToolResultPresenterRegistry
from dojoagents.agent.models import ToolCall, ToolResult, ToolResultList
from dojoagents.tools.registry import ToolRegistry
from dojoagents.tools.sandbox import SandboxPolicy
from dojoagents.logging import LOGGER


class ToolExecutor:
    def __init__(self, registry: ToolRegistry, sandbox: SandboxPolicy) -> None:
        self.registry = registry
        self.sandbox = sandbox
        self.presenters = ToolResultPresenterRegistry()

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
        try:
            self.sandbox.check_tool(call.name)
            started_at = time.perf_counter()
            raw = await asyncio.wait_for(
                spec.handler(dict(call.arguments)),
                timeout=self.sandbox.timeout_seconds,
            )
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            return self._coerce_result(call, raw, session_id=session_id, latency_ms=latency_ms)
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
        normalized = self.presenters.normalize(call.name, normalized)

        content = str(normalized.get("content", ""))
        metadata = dict(normalized.get("metadata", {}))
        if session_id:
            metadata.setdefault("session_id", session_id)
        return ToolResult(
            call_id=call.id,
            name=call.name,
            ok=True,
            content=content,
            latency_ms=latency_ms,
            truncated=bool(normalized.get("truncated", False)),
            data=normalized.get("data"),
            viz_blocks=list(normalized.get("viz_blocks", [])),
            artifacts=list(normalized.get("artifacts", [])),
            resource_changes=list(normalized.get("resource_changes", [])),
            metadata=metadata,
        )
