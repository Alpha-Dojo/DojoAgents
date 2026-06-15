"""Event-driven activation hooks for multi-agent orchestration."""

from __future__ import annotations

import re
from typing import Any


COMPLEXITY_TRIGGERS = [
    {
        "pattern": r"(analyze|research|investigate).+(and|then).+(implement|build|create)",
        "confidence": 0.8,
    },
    {
        "pattern": r"(backtest|optimize).+(strategy|portfolio)",
        "confidence": 0.9,
    },
    {
        "pattern": r"(compare|evaluate).+multiple",
        "confidence": 0.7,
    },
]

TOOL_RESULT_TRIGGERS = [
    {
        "tool": "dojo_market_data",
        "result_pattern": r"multiple_assets|large_dataset",
        "action": "spawn_analyst",
    },
    {
        "tool": "code_execution",
        "result_pattern": r"error|failed",
        "action": "spawn_reviewer",
    },
]


class MultiAgentTriggerHook:
    """Plugin hook that detects when to activate multi-agent orchestration."""

    def __init__(self, orchestrator: Any) -> None:
        self._orchestrator = orchestrator

    def get_orchestration_prompt(self) -> str:
        """Return the orchestration prompt from the orchestrator."""
        if hasattr(self._orchestrator, "get_orchestration_prompt"):
            return self._orchestrator.get_orchestration_prompt()
        return ""

    def on_pre_llm_call(self, user_message: str, session_id: str, **kwargs: Any) -> str | None:
        """Inject orchestration context if complexity detected."""
        for trigger in COMPLEXITY_TRIGGERS:
            if re.search(trigger["pattern"], user_message, re.IGNORECASE):
                return self.get_orchestration_prompt()
        return None

    def on_post_tool_call(self, tool_name: str, result: str, session_id: str, **kwargs: Any) -> None:
        """React to tool results that suggest multi-agent is needed."""
        for trigger in TOOL_RESULT_TRIGGERS:
            if trigger["tool"] == tool_name:
                if re.search(trigger["result_pattern"], result, re.IGNORECASE):
                    self._orchestrator.activate(trigger["action"], session_id)
