from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from dojoagents.quant.context import QuantContext
from dojoagents.tools.registry import ToolSpec


@dataclass(frozen=True)
class ExtensionHealth:
    ok: bool
    message: str = "ok"


@dataclass(frozen=True)
class DashboardCardSpec:
    id: str
    title: str
    payload: dict[str, Any] = field(default_factory=dict)


class DojoExtension(Protocol):
    name: str
    version: str
    specification: str

    def health(self) -> ExtensionHealth: ...

    def tool_specs(self) -> list[ToolSpec]: ...
    
    def execute_command(self, command: str) -> str: ...

    def dashboard_cards(self) -> list[DashboardCardSpec]: ...

    def prompt_context(self, quant_context: QuantContext) -> str: ...
