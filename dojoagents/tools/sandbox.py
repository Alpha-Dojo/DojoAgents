from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SandboxPolicy:
    allowed_roots: list[str] = field(default_factory=list)
    allow_network: bool = False
    allowed_commands: list[str] = field(default_factory=list)
    timeout_seconds: float = 120

    def check_tool(self, _tool_name: str) -> None:
        return None
