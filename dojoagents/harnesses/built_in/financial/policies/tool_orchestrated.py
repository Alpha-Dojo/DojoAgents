from dojoagents.agent.harnesses.tool_orchestrated import ToolOrchestratedHarness
from dojoagents.harnesses.decisions import CompletionDecision, ToolControlDecision

from ..state import _legacy_state


class ToolOrchestratedTaskPolicy:
    def __init__(self, *, task_output_root: str) -> None:
        self._legacy = ToolOrchestratedHarness(task_output_root=task_output_root)

    async def authorize(self, call, context):
        message = self._legacy.block_tool_call(call, _legacy_state(context))
        return ToolControlDecision("block", "task_tool_blocked", message) if message else ToolControlDecision("allow", "task_tool_allowed")

    async def evaluate_completion(self, context):
        legacy = _legacy_state(context)
        if not self._legacy.matches(context.request, legacy):
            return CompletionDecision("continue", "tool_task_not_active")
        decision = self._legacy.validate_progress(legacy)
        if decision.complete:
            return CompletionDecision("continue", "tool_task_complete")
        return CompletionDecision(
            "recover",
            decision.stop_code,
            issues=tuple(decision.issues),
            recovery_prompt=self._legacy.build_recovery_prompt(decision, str(context.request.metadata.get("locale") or "en")),
            max_extra_turns=1,
        )


__all__ = ["ToolOrchestratedTaskPolicy"]
