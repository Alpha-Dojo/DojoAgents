"""Prompt contributors for FinancialHarness."""

from __future__ import annotations

from dojoagents.agent.temporal_context import build_temporal_context_block
from dojoagents.agent.turn_intent import TurnIntentResult, build_turn_intent_anchor

from .dashboard import dashboard_tool_prompt
from .identity import FINANCIAL_IDENTITY, financial_instructions_prompt, identity_prompt
from .visualization import visualization_prompt


def temporal_prompt(context) -> str:
    return build_temporal_context_block(context.request.metadata)


def request_context_prompt(context) -> str:
    contexts = context.turn_state.values.get("request_contexts", {})
    financial = contexts.get("financial.context-codec")
    return financial.prompt_block() if financial is not None else ""


def task_context_prompt(context) -> str:
    value = context.request.metadata.get("active_task_prompt")
    return value if isinstance(value, str) else ""


def turn_scope_prompt(context) -> str:
    request = context.request
    raw = request.metadata.get("_turn_intent_result")
    if isinstance(raw, dict):
        intent = TurnIntentResult(
            mode="continue_unfinished" if raw.get("continue_unfinished") else "new_task",
            prior_task_summary=str(raw.get("prior_task_summary") or ""),
            last_turn_status=str(raw.get("last_turn_status") or "unknown"),
        )
    else:
        intent = TurnIntentResult()
    return build_turn_intent_anchor(request, intent)


__all__ = [
    "FINANCIAL_IDENTITY",
    "dashboard_tool_prompt",
    "financial_instructions_prompt",
    "identity_prompt",
    "request_context_prompt",
    "task_context_prompt",
    "temporal_prompt",
    "turn_scope_prompt",
    "visualization_prompt",
]
