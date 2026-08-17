from dojoagents.harnesses.decisions import CompletionDecision


class FinancialTurnCompletionPolicy:
    async def evaluate_completion(self, context):
        return CompletionDecision("continue", "financial_policies_satisfied")


__all__ = ["FinancialTurnCompletionPolicy"]
