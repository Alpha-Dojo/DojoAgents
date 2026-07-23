from __future__ import annotations

from dojoagents.agent.harnesses.portfolio import PortfolioTaskHarness
from dojoagents.harnesses.decisions import CompletionDecision, ToolControlDecision

from ..state import _legacy_state, financial_turn_state


class PortfolioFlowPolicy:
    def __init__(self) -> None:
        self._legacy = PortfolioTaskHarness()

    async def before_turn(self, context) -> None:
        financial_turn_state(context)

    async def after_turn(self, context) -> None:
        state = financial_turn_state(context)
        persisted = context.session.state.values.setdefault("financial", {})
        if state.target_portfolio_id:
            persisted["target_portfolio_id"] = state.target_portfolio_id
        if state.sector_context:
            persisted["sector_context"] = dict(state.sector_context)

    async def authorize(self, call, context) -> ToolControlDecision:
        message = self._legacy.block_tool_call(call, _legacy_state(context))
        if message:
            return ToolControlDecision("block", "financial_portfolio_flow", message)
        return ToolControlDecision("allow", "financial_portfolio_allowed")

    async def evaluate_completion(self, context) -> CompletionDecision:
        legacy = _legacy_state(context)
        if not self._legacy.matches(context.request, legacy):
            return CompletionDecision("continue", "portfolio_not_active")
        decision = self._legacy.validate_progress(legacy)
        if decision.complete:
            return CompletionDecision("continue", "portfolio_complete")
        if decision.stop_code == "needs_user_input":
            return CompletionDecision(
                "needs_user_input",
                decision.escalation_code or "needs_user_input",
                issues=tuple(decision.issues),
                context=decision.escalation_context,
            )
        recovery = self._legacy.build_recovery_prompt(decision, str(context.request.metadata.get("locale") or "en"))
        return CompletionDecision(
            "recover" if decision.allow_extra_steps else "blocked",
            decision.stop_code,
            issues=tuple(decision.issues),
            recovery_prompt=recovery,
            max_extra_turns=1 if decision.allow_extra_steps else 0,
        )


__all__ = ["PortfolioFlowPolicy"]
