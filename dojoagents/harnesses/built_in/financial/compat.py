"""Compatibility adapter for the pre-Harness synchronous Runtime facade.

All financial behavior needed by ``Runtime.from_config_store`` lives here so
the generic AgentLoop does not import financial prompt or policy modules.
"""

from __future__ import annotations

from typing import Any

from dojoagents.agent.models import ChatRequest
from dojoagents.agent.guardrails import ToolGuardrailDecision
from dojoagents.agent.temporal_context import build_temporal_context_block

from .policies.legacy_harness import FinancialHarnessLoopState
from .policies.legacy_completion import apply_turn_completion_after_model
from .policies.legacy_completion_hook import TurnCompletionHook
from .policies.portfolio_tool_repair import merge_remove_holding_tool_calls
from .policies.sector_context import (
    record_sector_search_in_invocation,
    repair_sector_tool_arguments,
)
from .policies.turn_intent import build_turn_intent_anchor_async
from .policies.visualization_rules import (
    build_viz_policy_catalog,
    build_viz_policy_turn_anchor,
)
from .prompts.canvas_protocol import DASHBOARD_VIZ_PROTOCOL
from .prompts.dashboard_protocol import DASHBOARD_TOOL_PROTOCOL


class FinancialLegacyBehavior:
    """Own the financial-only branches still needed by the sync facade."""

    state_factory = FinancialHarnessLoopState

    @staticmethod
    def create_hook() -> TurnCompletionHook:
        return TurnCompletionHook()

    async def build_prompt_blocks(self, loop: Any, request: ChatRequest, model_id: str) -> list[str]:
        blocks = [
            "You are DojoAgents, a full-market finance analysis agent.",
            build_temporal_context_block(request.metadata),
            loop.skill_manager.prompt_block(platform=request.channel),
            loop.memory_manager.build_system_prompt(),
            await loop.memory_manager.prefetch_all(
                request.message,
                session_id=request.session_id,
            ),
        ]
        if request.quant is not None:
            blocks.append(request.quant.prompt_block())
            blocks.append(loop.extension_registry.prompt_context(request.quant))
        if request.channel == "dashboard":
            locale = str(request.metadata.get("locale") or "en")
            blocks.extend(
                [
                    DASHBOARD_VIZ_PROTOCOL,
                    DASHBOARD_TOOL_PROTOCOL,
                    build_viz_policy_catalog(locale),
                ]
            )
            anchor = build_viz_policy_turn_anchor(request, locale)
            if anchor:
                blocks.append(anchor)
        if loop.task_manager is not None:
            task_block = loop.task_manager.build_injection_block(request)
            if task_block:
                blocks.append(task_block)
        turn_anchor, _ = await build_turn_intent_anchor_async(
            request,
            loop.usage_llm_provider,
            model=model_id,
        )
        if turn_anchor:
            blocks.append(turn_anchor)
        return blocks

    def transform_model_result(self, llm_result: Any, invocation_state: dict[str, Any]) -> None:
        request = invocation_state.get("_dojo_request")
        if isinstance(request, ChatRequest) and request.channel == "dashboard":
            llm_result.tool_calls = merge_remove_holding_tool_calls(list(llm_result.tool_calls))
            apply_turn_completion_after_model(llm_result, invocation_state)

    def repair_tool_arguments(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        invocation_state: dict[str, Any],
    ) -> dict[str, Any]:
        return repair_sector_tool_arguments(tool_name, arguments, invocation_state)

    def record_tool_result(self, invocation_state: dict[str, Any], result: Any) -> None:
        record_sector_search_in_invocation(invocation_state, result)

    async def authorize_tool(
        self,
        loop: Any,
        request: ChatRequest,
        tool_name: str,
        arguments: dict[str, Any],
        model_id: str,
    ) -> ToolGuardrailDecision | None:
        from .policies.execute_code_guardrails import (
            EXECUTE_CODE_TOOL_NAMES,
            classify_execute_code,
            execute_code_guardrail_from_classification,
        )

        if tool_name not in EXECUTE_CODE_TOOL_NAMES:
            return None
        classification = await classify_execute_code(
            str(arguments.get("code") or ""),
            request.message,
            loop.usage_llm_provider,
            model=model_id,
            request_metadata=request.metadata,
        )
        blocked, message, code = execute_code_guardrail_from_classification(
            tool_name,
            classification,
        )
        if not blocked:
            return None
        return ToolGuardrailDecision(
            action="block",
            code=code,
            message=message,
            tool_name=tool_name,
        )


__all__ = ["FinancialLegacyBehavior"]
