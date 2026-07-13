from __future__ import annotations

from typing import Any

from dojoagents.agent.models import AgentResponse, ChatRequest
from dojoagents.logging import LOGGER
from dojoagents.tasks.activator import TaskActivator
from dojoagents.tasks.manager import TaskPromptManager
from dojoagents.tasks.models import ActiveTask, PipelineState, TaskArtifactSpec
from dojoagents.tasks.output_paths import normalize_task_id, resolve_task_output_file
from dojoagents.tasks.schema_validator import TaskOutputValidator


class PipelineAdvanceResult:
    def __init__(
        self,
        *,
        next_request: ChatRequest | None = None,
        validation_errors: list[str] | None = None,
        completed: bool = False,
    ) -> None:
        self.next_request = next_request
        self.validation_errors = list(validation_errors or [])
        self.completed = completed


class PipelineRunner:
    def __init__(
        self,
        *,
        manager: TaskPromptManager,
        activator: TaskActivator,
        validator: TaskOutputValidator,
        task_output_root: str,
    ) -> None:
        self.manager = manager
        self.activator = activator
        self.validator = validator
        self.task_output_root = task_output_root

    def maybe_advance(
        self,
        request: ChatRequest,
        response: AgentResponse,
    ) -> PipelineAdvanceResult:
        pipeline = PipelineState.from_metadata(request.metadata.get("pipeline"))
        active = ActiveTask.from_metadata(request.metadata.get("active_task"))
        if pipeline is None or active is None:
            return PipelineAdvanceResult()

        spec = self.manager.get_pipeline(pipeline.id)
        if spec is None or not spec.steps:
            return PipelineAdvanceResult()

        step_index = max(0, pipeline.step - 1)
        if step_index >= len(spec.steps):
            return PipelineAdvanceResult(completed=True)

        current_step = spec.steps[step_index]
        task_spec = self.manager.get_task(active.task_id)
        if task_spec is None:
            return PipelineAdvanceResult()

        output_errors = self._validate_outputs(task_spec, active)
        if output_errors:
            LOGGER.warning("Pipeline %s step %s output validation failed: %s", pipeline.id, pipeline.step, output_errors)
            return PipelineAdvanceResult(validation_errors=output_errors)

        for output_item in active.outputs:
            filename = str(output_item.get("filename") or "").strip()
            if not filename:
                continue
            try:
                path = resolve_task_output_file(self.task_output_root, active.task_id, filename)
            except ValueError:
                continue
            if path.is_file():
                pipeline.artifacts[filename] = str(path)

        if current_step.on_success != "continue" or pipeline.step >= len(spec.steps):
            return PipelineAdvanceResult(completed=True)

        next_step = spec.steps[pipeline.step]
        pipeline.step += 1
        next_request = ChatRequest(
            message=f"Continue pipeline {pipeline.id} step {pipeline.step}: {next_step.task}",
            user_id=request.user_id,
            session_id=request.session_id,
            channel=request.channel,
            quant=request.quant,
            metadata=dict(request.metadata),
        )
        next_request.metadata["pipeline"] = pipeline.to_metadata()
        next_request.metadata.pop("active_task", None)
        try:
            activated = self.activator.activate_task(
                next_request,
                task_id=next_step.task,
                params=dict(pipeline.params),
                pipeline=pipeline,
            )
        except Exception as exc:
            LOGGER.exception("Failed to activate pipeline step %s for %s", pipeline.step, pipeline.id)
            return PipelineAdvanceResult(validation_errors=[str(exc)])
        return PipelineAdvanceResult(next_request=activated)

    def _validate_outputs(self, task_spec: Any, active: ActiveTask) -> list[str]:
        issues: list[str] = []
        task_id = normalize_task_id(active.task_id)
        for output_item in active.outputs:
            filename = str(output_item.get("filename") or "").strip()
            if not filename:
                continue
            schema = output_item.get("schema")
            artifact = TaskArtifactSpec(
                filename=filename,
                format=str(output_item.get("format") or "json"),
                required=bool(output_item.get("required", True)),
                schema=str(schema) if schema else None,
            )
            try:
                path = resolve_task_output_file(self.task_output_root, task_id, filename)
            except ValueError as exc:
                issues.append(str(exc))
                continue
            if not path.is_file():
                issues.append(f"Missing required output: {filename}")
                continue
            issues.extend(
                self.validator.validate_artifact(task=task_spec, artifact=artifact, path=path)
            )
        return issues
