from __future__ import annotations

import re
from dataclasses import replace

from ..legacy_harness import HarnessDecision, HarnessLoopState, TaskHarness
from dojoagents.agent.models import ChatRequest, ToolCall, ToolResult
from dojoagents.tasks.harness_validation import TaskOutputHarnessMixin, build_schema_recovery_prompt
from dojoagents.tasks.manager import TaskPromptManager
from dojoagents.tasks.models import ActiveTask

_EVENT_JSON_RE = re.compile(r"\{\s*\"event_time\"")


class ArtifactSynthesisHarness(TaskOutputHarnessMixin, TaskHarness):
    name = "artifact_synthesis"

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
        return active is not None and (active.harness_profile == self.name or active.harness_profile == "artifact_synthesis")

    def repair_tool_calls(self, calls: list[ToolCall], state: HarnessLoopState) -> list[ToolCall]:
        active = ActiveTask.from_metadata(state.request.metadata.get("active_task"))
        if active is None:
            return calls
        repaired: list[ToolCall] = []
        for call in calls:
            if call.name != "read_session_output":
                repaired.append(call)
                continue
            args = dict(call.arguments or {})
            filename = str(args.get("filename") or "").strip()
            if not filename:
                repaired.append(call)
                continue
            for item in active.inputs:
                base = str(item.get("base_filename") or "").strip()
                resolved = str(item.get("filename") or "").strip()
                if filename == base and resolved and filename != resolved:
                    args["filename"] = resolved
                    call = replace(call, arguments=args)
                    break
            repaired.append(call)
        return repaired

    def block_tool_call(self, call: ToolCall, state: HarnessLoopState) -> str | None:
        active = ActiveTask.from_metadata(state.request.metadata.get("active_task"))
        if active is None:
            return None

        self._sync_input_reads(active, state)
        state.request.metadata["active_task"] = active.to_metadata()

        if call.name == "write_session_file" and active.constraints.get("must_read_input_before_write", True):
            required_inputs = [str(item.get("filename") or "") for item in active.inputs if item.get("required", True)]
            missing = [name for name in required_inputs if name and name not in active.input_read]
            if missing:
                return "Call read_session_output for required inputs before write_session_file: " + ", ".join(missing)
        return None

    def validate_progress(self, state: HarnessLoopState) -> HarnessDecision:
        active = ActiveTask.from_metadata(state.request.metadata.get("active_task"))
        if active is None:
            return HarnessDecision()

        self._sync_input_reads(active, state)
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
        required_inputs = [str(item.get("filename") or "") for item in active.inputs if item.get("required", True)]
        unread = [name for name in required_inputs if name and name not in active.input_read]
        if unread:
            issues.append(f"Read input files first: {', '.join(unread)}")
        elif not self._has_tool(state, "write_session_file"):
            issues.append("Write the required JSONL output with write_session_file. " "A markdown attribution table in chat does not count as task completion.")

        if active.constraints.get("forbid_full_json_in_chat") and _EVENT_JSON_RE.search(state.final_response or ""):
            issues.append("Do not paste full event JSON in chat; write the required JSONL output file instead.")

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
            return f"任务未完成。{issue}"
        return f"Task incomplete. {issue}"

    def _sync_input_reads(self, active: ActiveTask, state: HarnessLoopState) -> None:
        self._track_reads(active, state.tool_results)
        for entry in state.tool_trace:
            if not entry.get("ok") or str(entry.get("tool") or "") != "read_session_output":
                continue
            args = entry.get("arguments")
            if not isinstance(args, dict):
                continue
            read_name = str(args.get("filename") or "").strip()
            if not read_name:
                continue
            for item in active.inputs:
                resolved = str(item.get("filename") or "").strip()
                base = str(item.get("base_filename") or "").strip()
                if read_name in {resolved, base} and resolved:
                    active.input_read.add(resolved)

    def _track_reads(self, active: ActiveTask, results: list[ToolResult]) -> None:
        for result in results:
            if not result.ok or result.name != "read_session_output":
                continue
            filename = self._read_result_filename(result)
            if not filename:
                continue
            for item in active.inputs:
                resolved = str(item.get("filename") or "").strip()
                base = str(item.get("base_filename") or "").strip()
                if filename in {resolved, base} and resolved:
                    active.input_read.add(resolved)
                    break

    @staticmethod
    def _read_result_filename(result: ToolResult) -> str | None:
        data = result.data
        if isinstance(data, dict):
            filename = data.get("filename")
            if filename:
                return str(filename).strip() or None
        metadata = result.metadata
        if isinstance(metadata, dict):
            filename = metadata.get("filename")
            if filename:
                return str(filename).strip() or None
        return None

    @staticmethod
    def _has_tool(state: HarnessLoopState, tool_name: str) -> bool:
        return any(result.ok and result.name == tool_name for result in state.tool_results)
