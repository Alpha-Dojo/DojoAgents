from __future__ import annotations

from ..legacy_harness import HarnessDecision, HarnessLoopState, TaskHarness
from dojoagents.agent.models import ChatRequest, ToolCall
from dojoagents.tasks.harness_validation import TaskOutputHarnessMixin, build_schema_recovery_prompt
from dojoagents.tasks.manager import TaskPromptManager
from dojoagents.tasks.models import ActiveTask

_FORBIDDEN_DAYS_TOOLS = frozenset({"get_market_overview", "get_sector_movers"})


class ToolOrchestratedHarness(TaskOutputHarnessMixin, TaskHarness):
    name = "tool_orchestrated"

    def __init__(
        self,
        *,
        task_manager: TaskPromptManager | None = None,
        task_output_root: str = "~/.dojo/tasks/outputs",
    ) -> None:
        self.task_manager = task_manager
        self.task_output_root = task_output_root

    def matches(self, request: ChatRequest, state: HarnessLoopState) -> bool:
        active = ActiveTask.from_metadata(request.metadata.get("active_task"))
        return active is not None and (active.harness_profile == self.name or active.harness_profile == "tool_orchestrated")

    def repair_tool_calls(self, calls: list[ToolCall], state: HarnessLoopState) -> list[ToolCall]:
        active = ActiveTask.from_metadata(state.request.metadata.get("active_task"))
        if active is None:
            return calls
        max_per_turn = int(active.constraints.get("max_tool_calls_per_turn", 1) or 1)
        if len(calls) > max_per_turn:
            return calls[:max_per_turn]
        return calls

    def block_tool_call(self, call: ToolCall, state: HarnessLoopState) -> str | None:
        active = ActiveTask.from_metadata(state.request.metadata.get("active_task"))
        if active is None:
            return None

        if call.name in _FORBIDDEN_DAYS_TOOLS:
            args = call.arguments or {}
            if "days" in args and not args.get("start_date"):
                return f"{call.name}: omit `days` in task mode; use start_date/end_date from task params."

        tool_budget = active.constraints.get("tool_budget")
        if isinstance(tool_budget, dict) and call.name in tool_budget:
            used = int(active.tool_budget_used.get(call.name, 0))
            limit = int(tool_budget[call.name])
            if used >= limit:
                return f"Tool budget exceeded for {call.name} ({used}/{limit})."

        return None

    def validate_progress(self, state: HarnessLoopState) -> HarnessDecision:
        active = ActiveTask.from_metadata(state.request.metadata.get("active_task"))
        if active is None:
            return HarnessDecision()

        self._sync_tool_budget(active, state)
        state.request.metadata["active_task"] = active.to_metadata()

        filename, validation_issues = self._output_write_issues(state)
        if filename and not validation_issues:
            return HarnessDecision(complete=True)
        if validation_issues:
            return HarnessDecision(
                complete=False,
                issues=validation_issues,
                next_steps=validation_issues[:1],
                allow_extra_steps=True,
                stop_code="task_output_invalid",
            )

        issues: list[str] = []
        if not state.tool_results:
            issues.append("Start with get_market_overview using start_date/end_date.")
        elif not self._has_tool(state, "get_sector_movers"):
            issues.append("Call get_sector_movers before web_search.")
        elif not self._has_tool(state, "write_session_file"):
            issues.append("Finish by writing the required output file with write_session_file.")

        return HarnessDecision(
            complete=False,
            issues=issues,
            next_steps=issues[:1],
            allow_extra_steps=True,
            stop_code="task_incomplete",
        )

    def build_recovery_prompt(self, decision: HarnessDecision, locale: str) -> str:
        if decision.stop_code == "task_output_invalid" and decision.issues:
            return build_schema_recovery_prompt(
                filename="required output",
                issues=decision.issues,
                locale=locale,
            )
        issue = decision.next_steps[0] if decision.next_steps else (decision.issues[0] if decision.issues else "")
        if locale == "zh":
            return f"任务未完成。{issue} 每次只调用一个工具。"
        return f"Task incomplete. {issue} Call only one tool per turn."

    def _sync_tool_budget(self, active: ActiveTask, state: HarnessLoopState) -> None:
        counts: dict[str, int] = {}
        for entry in state.tool_trace:
            name = str(entry.get("name") or "").strip()
            if name:
                counts[name] = counts.get(name, 0) + 1
        active.tool_budget_used = counts

    @staticmethod
    def _has_tool(state: HarnessLoopState, tool_name: str) -> bool:
        return any(result.ok and result.name == tool_name for result in state.tool_results)
