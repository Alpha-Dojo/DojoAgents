from __future__ import annotations

from pathlib import Path
from typing import Any

from dojoagents.agent.harness import HarnessDecision, HarnessLoopState, TaskHarness
from dojoagents.agent.models import ChatRequest, ToolCall, ToolResult
from dojoagents.agent.write_session_file_guardrails import active_task_metadata
from dojoagents.tasks.manager import TaskPromptManager
from dojoagents.tasks.models import ActiveTask, TaskArtifactSpec
from dojoagents.tasks.output_validation import (
    find_output_artifact,
    validate_task_output_file,
)


class TaskOutputHarnessMixin:
    task_manager: TaskPromptManager | None
    task_output_root: str

    def _validate_written_output(
        self,
        *,
        active: ActiveTask,
        result: ToolResult,
        filename: str,
    ) -> list[str]:
        if self.task_manager is None:
            return []
        active_meta = active_task_metadata({"active_task": active.to_metadata()})
        if not isinstance(active_meta, dict):
            return ["Active task metadata missing"]

        artifact_meta = find_output_artifact(active_meta, filename)
        if artifact_meta is None:
            return [f"Unexpected output filename: {filename}"]

        path_text = None
        data = result.data
        if isinstance(data, dict):
            path_text = data.get("path")
        if not path_text:
            return ["write_session_file result missing output path"]

        path = Path(str(path_text))
        if not path.is_file():
            return [f"Output file not found after write: {path.name}"]

        spec = self.task_manager.get_task(active.task_id)
        if spec is None:
            return [f"Unknown task: {active.task_id}"]

        artifact = TaskArtifactSpec(
            filename=filename,
            format=str(artifact_meta.get("format") or "json"),
            required=bool(artifact_meta.get("required", True)),
            schema=str(artifact_meta["schema"]).strip() if artifact_meta.get("schema") else None,
        )
        return validate_task_output_file(
            manager=self.task_manager,
            task=spec,
            artifact=artifact,
            path=path,
        )

    def _output_write_issues(self, state: HarnessLoopState) -> tuple[str | None, list[str]]:
        active = ActiveTask.from_metadata(state.request.metadata.get("active_task"))
        if active is None:
            return None, []

        expected_outputs = {str(item.get("filename") or "") for item in active.outputs}
        for result in reversed(state.tool_results):
            if not result.ok or result.name != "write_session_file":
                continue
            filename = self._write_filename(result)
            if not filename or filename not in expected_outputs:
                continue
            issues = self._validate_written_output(active=active, result=result, filename=filename)
            if not issues:
                return filename, []
            return filename, issues
        return None, []

    @staticmethod
    def _write_filename(result: ToolResult) -> str | None:
        data = result.data
        if isinstance(data, dict) and data.get("filename"):
            return str(data["filename"])
        return None


def build_schema_recovery_prompt(*, filename: str, issues: list[str], locale: str) -> str:
    detail = "; ".join(issues[:3])
    if locale == "zh":
        return (
            f"任务产出未通过校验：{filename}。{detail} "
            "请用 write_session_file 重新写入完整 schema 数据，禁止只写路径说明或占位 JSON。"
        )
    return (
        f"Task output failed validation: {filename}. {detail} "
        "Rewrite the full schema payload with write_session_file. "
        "Do not write path notes or placeholder JSON."
    )
