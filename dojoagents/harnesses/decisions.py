"""Structured decisions returned by harness control-flow hooks."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping


def _require_code(code: str) -> None:
    if not code.strip():
        raise ValueError("decision code must not be blank")


@dataclass(frozen=True)
class ToolControlDecision:
    """A harness decision made before or after tool execution."""

    action: str
    code: str
    message: str = ""
    context: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.action not in {"allow", "block", "halt", "needs_user_input"}:
            raise ValueError(f"unsupported tool control action: {self.action}")
        _require_code(self.code)
        object.__setattr__(self, "context", MappingProxyType(dict(self.context)))


@dataclass(frozen=True)
class CompletionDecision:
    """A harness decision about whether and how a turn may finish."""

    action: str
    code: str
    issues: tuple[str, ...] = ()
    recovery_prompt: str = ""
    max_extra_turns: int = 0
    context: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.action not in {
            "continue",
            "recover",
            "complete",
            "blocked",
            "needs_user_input",
        }:
            raise ValueError(f"unsupported completion action: {self.action}")
        _require_code(self.code)
        if not 0 <= self.max_extra_turns <= 100:
            raise ValueError("max_extra_turns must be between 0 and 100")
        object.__setattr__(self, "issues", tuple(self.issues))
        object.__setattr__(self, "context", MappingProxyType(dict(self.context)))
