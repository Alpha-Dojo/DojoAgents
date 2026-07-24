from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from dojoagents.agent.models import ChatRequest
from dojoagents.logging import LOGGER
from dojoagents.skills.manager import SkillManager
from dojoagents.tasks.activator import TaskActivationError, TaskActivator, parse_task_params
from dojoagents.tasks.manager import TaskPromptManager
from dojoagents.tasks.models import PipelineState

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class CommandRouter:
    """Shared slash-command and metadata preprocessing for all channels."""

    def __init__(
        self,
        *,
        manager: TaskPromptManager,
        activator: TaskActivator,
        skill_manager: SkillManager | None = None,
    ) -> None:
        self.manager = manager
        self.activator = activator
        self.skill_manager = skill_manager

    def preprocess(self, request: ChatRequest) -> ChatRequest:
        if isinstance(request.metadata.get("active_task"), dict):
            return request

        raw_pipeline = request.metadata.get("pipeline")
        if isinstance(raw_pipeline, dict) and raw_pipeline.get("id"):
            return request

        pipeline_id = request.metadata.get("pipeline_id")
        if isinstance(pipeline_id, str) and pipeline_id.strip():
            return self._activate_pipeline(request, pipeline_id.strip(), request.metadata.get("pipeline_params"))

        task_type = request.metadata.get("task_type")
        if isinstance(task_type, str) and task_type.strip():
            params = request.metadata.get("task_params")
            return self._safe_activate(
                request,
                task_id=task_type.strip(),
                params=dict(params) if isinstance(params, dict) else parse_task_params(request.message),
            )

        text = str(request.message or "").strip()
        if text.startswith("/"):
            return self._handle_slash_command(request, text)

        detected = self.activator.try_keyword_activation(request)
        return detected or request

    def _handle_slash_command(self, request: ChatRequest, text: str) -> ChatRequest:
        name, _, arg = text[1:].partition(" ")
        name = name.lower().replace("_", "-")
        if name in {"task"}:
            task_id, _, task_arg = arg.strip().partition(" ")
            task_id = task_id.strip()
            if not task_id:
                raise TaskActivationError("Usage: /task <task-id> [YYYY-MM-DD]")
            return self._safe_activate(request, task_id=task_id, params=parse_task_params(task_arg))
        if name in {"pipeline"}:
            pipeline_id, _, pipeline_arg = arg.strip().partition(" ")
            pipeline_id = pipeline_id.strip()
            if not pipeline_id:
                raise TaskActivationError("Usage: /pipeline <pipeline-id> [YYYY-MM-DD]")
            return self._activate_pipeline(request, pipeline_id, parse_task_params(pipeline_arg))
        if name in {"skill"}:
            skill_name, _, skill_arg = arg.strip().partition(" ")
            return self._load_skill(request, skill_name.strip(), skill_arg.strip())
        if self.skill_manager is not None and name in set(self.skill_manager.list_skills()):
            return self._load_skill(request, name, arg.strip())
        available_tasks = ", ".join(self.manager.list_tasks()) or "(none)"
        available_skills = ", ".join(self.skill_manager.list_skills()) if self.skill_manager else "(none)"
        raise TaskActivationError(f"Unknown command `/{name}`. Available tasks: {available_tasks}. Available skills: {available_skills}.")

    def _activate_pipeline(
        self,
        request: ChatRequest,
        pipeline_id: str,
        params: Any,
    ) -> ChatRequest:
        pipeline = self.manager.get_pipeline(pipeline_id)
        if pipeline is None or not pipeline.steps:
            raise TaskActivationError(f"Unknown pipeline: {pipeline_id}")
        merged_params = dict(params) if isinstance(params, dict) else parse_task_params(str(params or ""))
        state = PipelineState(id=pipeline.id, step=1, params=merged_params)
        first = pipeline.steps[0]
        request = replace(request, message=f"Run pipeline {pipeline.id} step 1: {first.task}")
        return self._safe_activate(request, task_id=first.task, params=merged_params, pipeline=state)

    def _safe_activate(
        self,
        request: ChatRequest,
        *,
        task_id: str,
        params: dict[str, Any] | None = None,
        pipeline: PipelineState | None = None,
    ) -> ChatRequest:
        try:
            activated = self.activator.activate_task(
                request,
                task_id=task_id,
                params=params,
                pipeline=pipeline,
            )
        except TaskActivationError:
            raise
        except Exception as exc:
            LOGGER.exception("Task activation failed for %s", task_id)
            raise TaskActivationError(str(exc)) from exc
        if not str(activated.message or "").strip():
            spec = self.manager.get_task(task_id)
            label = spec.contract.name if spec else task_id
            activated = replace(activated, message=f"Execute task: {label}")
        metadata = dict(activated.metadata)
        metadata["task_command"] = task_id
        return replace(activated, metadata=metadata)

    def _load_skill(self, request: ChatRequest, skill_name: str, arg: str) -> ChatRequest:
        if not skill_name:
            raise TaskActivationError("Usage: /skill <name> [instruction]")
        if self.skill_manager is None:
            raise TaskActivationError("Skill manager is not configured")
        available = set(self.skill_manager.list_skills())
        if skill_name not in available:
            raise TaskActivationError(f"Unknown skill: {skill_name}")
        skill_file = None
        for root in self.skill_manager.skill_dirs:
            candidate = root / skill_name / "SKILL.md"
            if candidate.is_file():
                skill_file = candidate
                break
        if skill_file is None:
            raise TaskActivationError(f"Skill file not found: {skill_name}")
        frontmatter, body = self.skill_manager._get_skill_content(skill_file)
        resolved_name = str(frontmatter.get("name") or skill_name)
        parts = [
            f'[IMPORTANT: The user invoked skill "{resolved_name}". Follow its instructions.]',
            "",
            body.strip(),
        ]
        if arg.strip():
            parts.extend(["", f"User instruction: {arg.strip()}"])
        metadata = dict(request.metadata)
        metadata["invoked_skill"] = resolved_name
        return replace(request, message="\n".join(parts), metadata=metadata)
