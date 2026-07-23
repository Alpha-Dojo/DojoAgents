from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from dojoagents.agent.models import ChatRequest
from dojoagents.tasks.artifacts import artifact_dicts_for_task, resolve_artifact_filename
from dojoagents.tasks.manager import TaskPromptManager
from dojoagents.tasks.models import ActiveTask, PipelineState, TaskSpec
from dojoagents.tasks.output_paths import (
    find_upstream_task_for_input,
    normalize_task_id,
    resolve_task_input_file,
)

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class TaskActivationError(ValueError):
    pass


def _normalize_task_id(raw: str) -> str:
    return normalize_task_id(raw)


def parse_task_params(arg: str) -> dict[str, Any]:
    text = str(arg or "").strip()
    if not text:
        return {}
    parts = text.split()
    params: dict[str, Any] = {}
    for token in parts:
        if _DATE_RE.fullmatch(token):
            params.setdefault("trading_date", token)
            params.setdefault("window_start_date", token)
            params.setdefault("window_end_date", token)
            continue
        if "=" in token:
            key, _, value = token.partition("=")
            key = key.strip()
            value = value.strip()
            if key:
                params[key] = value
    return params


def _artifact_dicts(
    manager: TaskPromptManager,
    spec: TaskSpec,
    *,
    kind: str,
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    items = artifact_dicts_for_task(spec, kind=kind, params=params)
    if kind != "input":
        return items
    enriched: list[dict[str, Any]] = []
    for item, artifact in zip(items, spec.contract.inputs):
        entry = dict(item)
        source_task = find_upstream_task_for_input(manager, spec, artifact)
        if source_task:
            entry["source_task_id"] = source_task
        enriched.append(entry)
    return enriched


class TaskActivator:
    def __init__(
        self,
        *,
        manager: TaskPromptManager,
        sessions_root: str,
        task_output_root: str,
        auto_detect: bool = False,
    ) -> None:
        self.manager = manager
        self.sessions_root = sessions_root
        self.task_output_root = task_output_root
        self.auto_detect = auto_detect

    def activate_task(
        self,
        request: ChatRequest,
        *,
        task_id: str,
        params: dict[str, Any] | None = None,
        pipeline: PipelineState | None = None,
    ) -> ChatRequest:
        normalized_id = _normalize_task_id(task_id)
        spec = self.manager.get_task(normalized_id)
        if spec is None:
            raise TaskActivationError(f"Unknown task: {task_id}")

        merged_params = dict(params or {})
        self._apply_defaults(request, merged_params)
        self._validate_params(merged_params)
        self._validate_inputs(spec, merged_params)

        active = ActiveTask(
            task_id=spec.contract.id,
            params=merged_params,
            harness_profile=spec.contract.harness_profile,
            constraints=dict(spec.contract.constraints),
            inputs=_artifact_dicts(self.manager, spec, kind="input", params=merged_params),
            outputs=_artifact_dicts(self.manager, spec, kind="output", params=merged_params),
        )
        metadata = dict(request.metadata)
        metadata["active_task"] = active.to_metadata()
        if pipeline is not None:
            metadata["pipeline"] = pipeline.to_metadata()
        metadata["task_mode"] = True
        return replace(request, metadata=metadata)

    def try_keyword_activation(self, request: ChatRequest) -> ChatRequest | None:
        if not self.auto_detect:
            return None
        message = str(request.message or "").lower()
        for task_id, spec in ((tid, self.manager.get_task(tid)) for tid in self.manager.list_tasks()):
            if spec is None:
                continue
            keywords = spec.contract.triggers.get("keywords") or []
            if not isinstance(keywords, list):
                continue
            if any(str(keyword).lower() in message for keyword in keywords if str(keyword).strip()):
                params = parse_task_params(request.message)
                return self.activate_task(request, task_id=task_id, params=params)
        return None

    def _apply_defaults(self, request: ChatRequest, params: dict[str, Any]) -> None:
        for key in ("trading_date", "window_start_date", "window_end_date"):
            if key in request.metadata:
                params.setdefault(key, request.metadata[key])
        if params.get("trading_date"):
            trading_date = str(params["trading_date"])
            params.setdefault("window_start_date", trading_date)
            params.setdefault("window_end_date", trading_date)

    def _validate_params(self, params: dict[str, Any]) -> None:
        for key in ("trading_date", "window_start_date", "window_end_date"):
            value = params.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text and not _DATE_RE.fullmatch(text):
                raise TaskActivationError(f"Invalid date for {key}: {value}")

    def _validate_inputs(self, spec: TaskSpec, params: dict[str, Any]) -> None:
        trading_date = str(params.get("trading_date") or "").strip()
        for artifact in spec.contract.inputs:
            if not artifact.required:
                continue
            resolved_name = resolve_artifact_filename(artifact, params)
            try:
                path = resolve_task_input_file(
                    manager=self.manager,
                    task_output_root=self.task_output_root,
                    consumer=spec,
                    artifact=artifact,
                    params=params,
                )
            except ValueError as exc:
                raise TaskActivationError(str(exc)) from exc
            if not path.is_file():
                raise TaskActivationError(f"Required input artifact not found: {resolved_name}. " f"Run the upstream task first.")
            if trading_date and artifact.format == "json":
                self._validate_trading_date(path, trading_date, resolved_name)

    def _validate_trading_date(self, path: Any, trading_date: str, filename: str) -> None:
        import json

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise TaskActivationError(f"Failed to read input artifact {filename}") from exc
        if not isinstance(payload, dict):
            return
        file_date = str(payload.get("trading_date") or "").strip()
        if file_date and file_date != trading_date:
            raise TaskActivationError(f"trading_date mismatch: request={trading_date}, {filename}={file_date}")
