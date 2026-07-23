from dojoagents.harnesses.decisions import CompletionDecision

from ..state import financial_turn_state


class FinancialTurnScopePolicy:
    async def before_turn(self, context):
        financial_turn_state(context)

    async def evaluate_completion(self, context):
        return CompletionDecision("continue", "turn_scope_satisfied")


__all__ = ["FinancialTurnScopePolicy"]
