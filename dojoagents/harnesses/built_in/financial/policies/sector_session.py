from .sector_context import (
    record_sector_search_in_invocation,
    repair_sector_tool_arguments,
)
from dojoagents.agent.models import ToolCall
from dojoagents.harnesses.decisions import CompletionDecision

from ..state import financial_turn_state


class SectorSessionPolicy:
    async def transform_calls(self, calls, context):
        invocation: dict = {}
        for result in context.tool_results:
            record_sector_search_in_invocation(invocation, result)
        repaired = []
        for call in calls:
            arguments = repair_sector_tool_arguments(call.name, call.arguments, invocation)
            repaired.append(call if arguments == call.arguments else ToolCall(call.id, call.name, arguments, dict(call.metadata)))
        return tuple(repaired)

    async def after_turn(self, context):
        state = financial_turn_state(context)
        if state.sector_context:
            context.session.state.values.setdefault("financial", {})["sector_context"] = dict(state.sector_context)

    async def evaluate_completion(self, context):
        return CompletionDecision("continue", "sector_session_recorded")


__all__ = ["SectorSessionPolicy"]
