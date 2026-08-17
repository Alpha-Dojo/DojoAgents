from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dojoagents.harnesses.components.task_flows import HarnessDecision, HarnessLoopState
from dojoagents.agent.models import ToolResult
from dojoagents.tools.write_authorization import active_task_metadata
from dojoagents.tasks.manager import TaskPromptManager
from dojoagents.tasks.models import ActiveTask, TaskArtifactSpec
from dojoagents.tasks.output_validation import (
    find_output_artifact,
    validate_task_output_file,
)
from dojoagents.tasks.write_contract import load_json_schema


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

        active_meta = active.to_metadata()
        for result in reversed(state.tool_results):
            if not result.ok or result.name != "write_session_file":
                continue
            filename = self._write_filename(result)
            if not filename or find_output_artifact(active_meta, filename) is None:
                continue
            issues = self._validate_written_output(active=active, result=result, filename=filename)
            if not issues:
                return filename, []
            return filename, issues
        return None, []

    def resolve_output_schema(
        self,
        active: ActiveTask,
        *,
        filename: str | None = None,
    ) -> tuple[str, dict[str, Any] | None]:
        """Return (output filename, loaded schema dict) for recovery prompts."""
        outputs = [item for item in active.outputs if isinstance(item, dict) and str(item.get("filename") or "").strip()]
        if not outputs:
            return (filename or "required output"), None

        target: dict[str, Any] | None = None
        wanted = str(filename or "").strip()
        if wanted:
            for item in outputs:
                if str(item.get("filename") or "").strip() == wanted:
                    target = item
                    break
        if target is None:
            target = outputs[0]

        out_name = str(target.get("filename") or wanted or "required output").strip()
        schema_ref = str(target.get("schema") or "").strip()
        if not schema_ref or self.task_manager is None:
            return out_name, None

        spec = self.task_manager.get_task(active.task_id)
        if spec is None:
            return out_name, None
        schema_path = self.task_manager.resolve_schema_path(spec, schema_ref)
        if schema_path is None:
            return out_name, None
        return out_name, load_json_schema(schema_path)

    def attach_output_schema_recovery(
        self,
        decision: HarnessDecision,
        active: ActiveTask,
        *,
        filename: str | None = None,
    ) -> HarnessDecision:
        """Stash the same schema used for validation onto the decision for recovery."""
        out_name, schema = self.resolve_output_schema(active, filename=filename)
        ctx = dict(decision.escalation_context)
        ctx["recovery_filename"] = out_name
        if schema is not None:
            ctx["recovery_schema"] = schema
        decision.escalation_context = ctx
        return decision

    @staticmethod
    def _write_filename(result: ToolResult) -> str | None:
        data = result.data
        if isinstance(data, dict) and data.get("filename"):
            return str(data["filename"])
        return None


def build_schema_recovery_prompt(
    *,
    filename: str,
    issues: list[str],
    locale: str,
    schema: dict[str, Any] | None = None,
) -> str:
    """Build recovery text: validation issues + the authoritative output schema."""
    detail = "; ".join(str(item).strip() for item in issues[:5] if str(item).strip())
    schema_block = ""
    if isinstance(schema, dict) and schema:
        schema_json = json.dumps(schema, ensure_ascii=False, indent=2)
        schema_block = (
            f"\n\nJSON Schema for `{filename}` (authoritative — content must satisfy this exactly):\n"
            f"```json\n{schema_json}\n```"
        )

    if locale == "zh":
        head = f"任务产出未通过校验：{filename}。"
        if detail:
            head += detail + " "
        head += "请用 write_session_file 按下列 schema 重新写入完整数据，禁止只写路径说明或占位 JSON。"
        return head + schema_block

    head = f"Task output failed validation: {filename}."
    if detail:
        head += f" {detail}"
    head += " Rewrite the full payload with write_session_file to satisfy the schema below. Do not write path notes or placeholder JSON."
    return head + schema_block
