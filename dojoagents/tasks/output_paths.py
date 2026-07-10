from __future__ import annotations

from pathlib import Path
from typing import Any

from dojoagents.agent.write_session_file_guardrails import active_task_metadata
from dojoagents.tasks.manager import TaskPromptManager
from dojoagents.tasks.models import TaskArtifactSpec, TaskSpec
from dojoagents.tools.session_file_names import validate_output_filename


def normalize_task_id(raw: str) -> str:
    return str(raw or "").strip().lower().replace("_", "-")


def resolve_task_output_dir(task_output_root: str | Path, task_id: str) -> Path:
    safe_task = normalize_task_id(task_id)
    if not safe_task:
        raise ValueError("task_id is required")
    root = Path(task_output_root).expanduser().resolve()
    output_dir = (root / safe_task).resolve()
    if output_dir.parent != root:
        raise ValueError(f"invalid task output directory for task_id: {task_id!r}")
    return output_dir


def resolve_task_output_file(
    task_output_root: str | Path,
    task_id: str,
    filename: str,
) -> Path:
    safe_name = validate_output_filename(filename)
    output_dir = resolve_task_output_dir(task_output_root, task_id)
    target = (output_dir / safe_name).resolve()
    if target.parent != output_dir:
        raise ValueError(f"invalid output path for filename: {filename!r}")
    return target


def find_upstream_task_for_input(
    manager: TaskPromptManager,
    consumer: TaskSpec,
    artifact: TaskArtifactSpec,
) -> str | None:
    if artifact.source_task:
        return normalize_task_id(artifact.source_task)
    for task_id in manager.list_tasks():
        upstream = manager.get_task(task_id)
        if upstream is None or upstream.contract.downstream != consumer.contract.id:
            continue
        for output in upstream.contract.outputs:
            if output.filename == artifact.filename:
                return normalize_task_id(task_id)
    return None


def resolve_task_input_file(
    *,
    manager: TaskPromptManager,
    task_output_root: str | Path,
    consumer: TaskSpec,
    artifact: TaskArtifactSpec,
    params: dict[str, Any] | None,
) -> Path:
    from dojoagents.tasks.artifacts import resolve_artifact_filename

    resolved_name = resolve_artifact_filename(artifact, params)
    source_task = find_upstream_task_for_input(manager, consumer, artifact)
    if not source_task:
        source_task = consumer.contract.id
    return resolve_task_output_file(task_output_root, source_task, resolved_name)


def resolve_task_read_path(
    *,
    task_output_root: str | Path,
    request_metadata: dict[str, Any] | None,
    filename: str,
) -> Path | None:
    active = active_task_metadata(request_metadata)
    if active is None:
        return None

    safe_name = validate_output_filename(filename)
    task_id = normalize_task_id(str(active.get("task_id") or ""))
    if not task_id:
        return None

    inputs = active.get("inputs")
    if isinstance(inputs, list):
        for item in inputs:
            if not isinstance(item, dict):
                continue
            if str(item.get("filename") or "").strip() != safe_name:
                continue
            source_task = normalize_task_id(
                str(item.get("source_task_id") or item.get("source_task") or task_id)
            )
            return resolve_task_output_file(task_output_root, source_task, safe_name)

    return resolve_task_output_file(task_output_root, task_id, safe_name)


def resolve_task_write_path(
    *,
    task_output_root: str | Path,
    request_metadata: dict[str, Any] | None,
    filename: str,
) -> Path | None:
    active = active_task_metadata(request_metadata)
    if active is None:
        return None

    task_id = normalize_task_id(str(active.get("task_id") or ""))
    if not task_id:
        return None

    safe_name = validate_output_filename(filename)
    return resolve_task_output_file(task_output_root, task_id, safe_name)
