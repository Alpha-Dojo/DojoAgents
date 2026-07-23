from .visualization_rules import build_viz_policy_context, check_agent_viz_build
from dojoagents.harnesses.decisions import CompletionDecision, ToolControlDecision


class FinancialVisualizationPolicy:
    async def authorize(self, call, context):
        if call.name != "agent_viz_build":
            return ToolControlDecision("allow", "not_visualization")
        decision = check_agent_viz_build(
            build_viz_policy_context(
                context.request,
                tool_results=context.tool_results,
                tool_trace=[item for item in context.trace if isinstance(item, dict)],
            )
        )
        if decision.block_agent_viz_build:
            return ToolControlDecision("block", decision.match.scene_id, decision.block_message)
        return ToolControlDecision("allow", decision.match.scene_id)

    async def evaluate_completion(self, context):
        return CompletionDecision("continue", "visualization_policy_satisfied")


__all__ = ["FinancialVisualizationPolicy"]
