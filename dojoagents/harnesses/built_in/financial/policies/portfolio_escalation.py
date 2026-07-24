from dojoagents.tools.escalation import find_user_input_escalation
from dojoagents.harnesses.decisions import CompletionDecision, ToolControlDecision


class PortfolioEscalationPolicy:
    _order_tools = frozenset({"portfolio_write_create_order", "portfolio_write_create_orders"})

    async def authorize(self, call, context):
        signal = find_user_input_escalation(context.tool_results)
        if signal is not None and call.name in self._order_tools:
            return ToolControlDecision("needs_user_input", signal.code, signal.message, signal.context)
        return ToolControlDecision("allow", "no_financial_escalation")

    async def evaluate_completion(self, context):
        signal = find_user_input_escalation(context.tool_results)
        if signal is None:
            return CompletionDecision("continue", "no_financial_escalation")
        return CompletionDecision(
            "needs_user_input",
            signal.code,
            issues=(signal.message,),
            context=signal.context,
        )


__all__ = ["PortfolioEscalationPolicy"]
