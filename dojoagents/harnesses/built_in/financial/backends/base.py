"""Stable agent-facing port for financial tool execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, runtime_checkable


@dataclass(frozen=True)
class FinancialToolDefinition:
    name: str
    description: str
    parameters: Mapping[str, Any]


@runtime_checkable
class FinancialToolBackend(Protocol):
    @property
    def supported_tools(self) -> frozenset[str]: ...

    @property
    def tool_definitions(self) -> Mapping[str, FinancialToolDefinition]:
        """Return transport-neutral schemas used to build Harness ToolSpecs."""

    async def execute(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        *,
        principal: Any,
        session_id: str,
    ) -> Mapping[str, Any]: ...


__all__ = ["FinancialToolBackend", "FinancialToolDefinition"]
