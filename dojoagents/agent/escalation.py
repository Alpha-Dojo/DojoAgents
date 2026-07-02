from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

STOP_CODE_NEEDS_USER_INPUT = "needs_user_input"

# Escalation codes that require user confirmation before the agent may continue.
USER_INPUT_ESCALATION_CODES = frozenset(
    {
        "capital_budget_exceeded",
        "invalid_order_quantity",
        "price_not_fillable",
    }
)


@dataclass(frozen=True)
class EscalationSignal:
    code: str
    message: str
    source_tool: str
    context: dict[str, Any] = field(default_factory=dict)
    recoverable_by_agent: bool = False


class AgentEscalationError(RuntimeError):
    """Structured tool failure that should stop agent auto-recovery and ask the user."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        context: dict[str, Any] | None = None,
        recoverable_by_agent: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.context = dict(context or {})
        self.recoverable_by_agent = recoverable_by_agent


def escalation_metadata(exc: AgentEscalationError, *, source_tool: str) -> dict[str, Any]:
    return {
        "escalation": {
            "code": exc.code,
            "message": exc.message,
            "source_tool": source_tool,
            "context": exc.context,
            "recoverable_by_agent": exc.recoverable_by_agent,
            "requires_user_input": exc.code in USER_INPUT_ESCALATION_CODES and not exc.recoverable_by_agent,
        }
    }


def escalation_from_metadata(metadata: dict[str, Any] | None) -> EscalationSignal | None:
    if not isinstance(metadata, dict):
        return None
    raw = metadata.get("escalation")
    if not isinstance(raw, dict):
        return None
    code = str(raw.get("code") or "").strip()
    if not code:
        return None
    return EscalationSignal(
        code=code,
        message=str(raw.get("message") or ""),
        source_tool=str(raw.get("source_tool") or ""),
        context=dict(raw.get("context") or {}) if isinstance(raw.get("context"), dict) else {},
        recoverable_by_agent=bool(raw.get("recoverable_by_agent")),
    )


def find_user_input_escalation(tool_results: list[Any]) -> EscalationSignal | None:
    """Return the latest escalation that should pause the loop for user input."""
    for result in reversed(tool_results):
        metadata = getattr(result, "metadata", None)
        signal = escalation_from_metadata(metadata if isinstance(metadata, dict) else None)
        if signal is None:
            continue
        if signal.code in USER_INPUT_ESCALATION_CODES and not signal.recoverable_by_agent:
            return signal
    return None
