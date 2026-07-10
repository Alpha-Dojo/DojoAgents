from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dojoagents.tasks.manager import TaskPromptManager
from dojoagents.tasks.models import TaskArtifactSpec, TaskSpec
from dojoagents.tasks.output_paths import resolve_task_output_file
from dojoagents.tasks.schema_validator import TaskOutputValidator, validate_json_payload


_PLACEHOLDER_MARKERS = frozenset(
    {
        "copy_of_task_output",
        "file_saved_at",
        "saved_at",
        "output_path",
        "path_note",
    }
)


def is_placeholder_task_output(content: Any, *, fmt: str) -> bool:
    normalized = str(fmt or "json").strip().lower()
    if normalized == "jsonl":
        if isinstance(content, list):
            rows = content
        elif isinstance(content, str):
            rows = [json.loads(line) for line in content.splitlines() if line.strip()]
        else:
            return False
        return bool(rows) and all(isinstance(row, dict) and _looks_like_placeholder_dict(row) for row in rows)

    payload: Any = content
    if isinstance(content, str):
        text = content.strip()
        if not text:
            return True
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return False
    if not isinstance(payload, dict):
        return False
    return _looks_like_placeholder_dict(payload)


def _looks_like_placeholder_dict(payload: dict[str, Any]) -> bool:
    keys = {str(key) for key in payload.keys()}
    if any(marker in keys for marker in _PLACEHOLDER_MARKERS):
        return True
    note = str(payload.get("note") or "").lower()
    if note and any(
        token in note
        for token in ("saved at", "also saved", "output path", "file path", "写入", "保存于")
    ):
        return True
    # Real task payloads always include trading_date; tiny meta-only dicts are not deliverables.
    if "trading_date" not in payload and "event_time" not in payload and len(keys) <= 3:
        return True
    return False


def find_output_artifact(active: dict[str, Any], filename: str) -> dict[str, Any] | None:
    outputs = active.get("outputs")
    if not isinstance(outputs, list):
        return None
    safe_name = str(filename or "").strip()
    for item in outputs:
        if isinstance(item, dict) and str(item.get("filename") or "").strip() == safe_name:
            return item
    return None


def validate_task_output_content(
    *,
    manager: TaskPromptManager,
    task_id: str,
    artifact_meta: dict[str, Any],
    content: Any,
    fmt: str,
) -> list[str]:
    issues: list[str] = []
    if is_placeholder_task_output(content, fmt=fmt):
        issues.append(
            "Refusing placeholder/meta-only output. Write the full task schema payload "
            "(sector_moves, news_items, event_summary, etc.), not path notes."
        )
        return issues

    schema_ref = str(artifact_meta.get("schema") or "").strip()
    if not schema_ref:
        return issues

    spec = manager.get_task(task_id)
    if spec is None:
        return [f"Unknown task: {task_id}"]

    artifact = TaskArtifactSpec(
        filename=str(artifact_meta.get("filename") or ""),
        format=str(artifact_meta.get("format") or fmt or "json"),
        required=bool(artifact_meta.get("required", True)),
        schema=schema_ref or None,
    )
    schema_path = manager.resolve_schema_path(spec, schema_ref)
    if schema_path is None:
        return [f"Schema not found: {schema_ref}"]

    normalized_fmt = str(fmt or artifact.format or "json").strip().lower()
    if normalized_fmt == "jsonl":
        if isinstance(content, list):
            lines = [json.dumps(item, ensure_ascii=False, separators=(",", ":")) for item in content]
            raw = "\n".join(lines) + ("\n" if lines else "")
        else:
            raw = str(content or "")
        from dojoagents.tasks.schema_validator import validate_jsonl_payload

        return validate_jsonl_payload(raw, schema_path)

    if isinstance(content, str):
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            return [f"Invalid JSON content: {exc.msg}"]
    else:
        payload = content
    return validate_json_payload(payload, schema_path)


def validate_task_output_file(
    *,
    manager: TaskPromptManager,
    task: TaskSpec,
    artifact: TaskArtifactSpec,
    path: Path,
) -> list[str]:
    return TaskOutputValidator(manager).validate_artifact(task=task, artifact=artifact, path=path)


def resolve_latest_task_output_path(
    *,
    task_output_root: str | Path,
    task_id: str,
    filename: str,
) -> Path:
    return resolve_task_output_file(task_output_root, task_id, filename)
