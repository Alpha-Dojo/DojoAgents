from __future__ import annotations

import asyncio
from typing import Any

from dojoagents.agent.models import ToolCall, ToolResult, ToolResultList
from dojoagents.tools.registry import ToolRegistry
from dojoagents.tools.sandbox import SandboxPolicy


class ToolExecutor:
    def __init__(self, registry: ToolRegistry, sandbox: SandboxPolicy) -> None:
        self.registry = registry
        self.sandbox = sandbox

    async def execute_many(
        self, tool_calls: list[ToolCall], *, session_id: str = ""
    ) -> ToolResultList:
        results = ToolResultList()
        if not tool_calls:
            return results

        tasks = [self.execute_one(call, session_id=session_id) for call in tool_calls]
        executed_results = await asyncio.gather(*tasks)
        for res in executed_results:
            results.append(res)
        return results

    async def execute_one(self, call: ToolCall, *, session_id: str = "") -> ToolResult:
        spec = self.registry.get(call.name)
        if spec is None:
            return ToolResult(
                call_id=call.id,
                name=call.name,
                ok=False,
                error=f"Tool '{call.name}' is not registered",
            )
        try:
            self.sandbox.check_tool(call.name)
            raw = await asyncio.wait_for(
                spec.handler(dict(call.arguments)),
                timeout=self.sandbox.timeout_seconds,
            )
            return self._coerce_result(call, raw, session_id=session_id)
        except Exception as exc:
            return ToolResult(
                call_id=call.id,
                name=call.name,
                ok=False,
                error=str(exc),
            )

    def _coerce_result(
        self, call: ToolCall, raw: dict[str, Any] | str | None, *, session_id: str
    ) -> ToolResult:
        if raw is None:
            content = ""
            metadata: dict[str, Any] = {}
        elif isinstance(raw, str):
            content = raw
            metadata = {}
        else:
            content = str(raw.get("content", ""))
            metadata = dict(raw.get("metadata", {}))
        if session_id:
            metadata.setdefault("session_id", session_id)
        return ToolResult(
            call_id=call.id,
            name=call.name,
            ok=True,
            content=content,
            metadata=metadata,
        )
