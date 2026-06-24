"""Automatic plan activation detection based on request complexity."""

from __future__ import annotations

import re
from typing import Any

from dojoagents.agent.models import ChatRequest


PLAN_PROMPT = (
    "You are in plan-driven execution mode. For this complex task, you should:\n"
    "1. Use the `create_plan` tool to create a structured execution plan\n"
    "2. Break the task into clear steps with dependencies\n"
    "3. Use `execute_plan` to run the plan step-by-step\n"
    "4. Use `revise_plan` if intermediate results require adjustments\n\n"
    "Each step should have a clear type: analysis, implementation, validation, decision, or delegation."
)


class PlanActivationHook:
    """Detects when automatic plan creation should be triggered."""

    COMPLEXITY_THRESHOLD = 100  # word count in user message
    MULTI_STEP_PATTERNS = [
        r"(first|step 1|phase 1).+(then|next|after)",
        r"(create|build|develop).+plan",
        r"(backtest|optimize|analyze).+(multiple|several|all)",
    ]

    def should_create_plan(self, request: ChatRequest) -> bool:
        """Determine if a plan should be auto-created."""
        # 1. Explicit plan request
        if "plan" in request.message.lower()[:50]:
            return True

        # 2. Workflow type from metadata (not QuantContext, which has no workflow_type)
        if request.metadata.get("workflow_type") == "backtest":
            return True

        # 3. Multi-step complexity detection
        for pattern in self.MULTI_STEP_PATTERNS:
            if re.search(pattern, request.message, re.IGNORECASE):
                return True

        # 4. Message length heuristic
        if len(request.message.split()) > self.COMPLEXITY_THRESHOLD:
            return True

        return False

    def get_plan_prompt(self) -> str:
        """Return system prompt instructions for plan-driven execution."""
        return PLAN_PROMPT
