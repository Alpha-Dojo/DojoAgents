from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from dojoagents.tasks.manager import TaskPromptManager
from dojoagents.tasks.models import TaskArtifactSpec, TaskSpec


class TaskSchemaValidationError(ValueError):
    pass


def _check_required_fields(payload: Any, schema: dict[str, Any], *, prefix: str = "") -> list[str]:
    issues: list[str] = []
    if schema.get("type") == "object" and isinstance(payload, dict):
        for key in schema.get("required") or []:
            if key not in payload:
                issues.append(f"{prefix}missing required field: {key}")
        properties = schema.get("properties") or {}
        if isinstance(properties, dict):
            for key, subschema in properties.items():
                if key in payload and isinstance(subschema, dict):
                    issues.extend(
                        _check_required_fields(
                            payload[key],
                            subschema,
                            prefix=f"{prefix}{key}.",
                        )
                    )
                if key in payload and isinstance(subschema, dict):
                    enum_values = subschema.get("enum")
                    if isinstance(enum_values, list) and payload[key] not in enum_values:
                        issues.append(
                            f"{prefix}{key}: invalid enum value {payload[key]!r}; expected one of {enum_values}"
                        )
                    pattern = subschema.get("pattern")
                    if pattern and isinstance(payload[key], str):
                        if not re.fullmatch(pattern, payload[key]):
                            issues.append(f"{prefix}{key}: value does not match pattern {pattern}")
    elif schema.get("type") == "array" and isinstance(payload, list):
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(payload):
                issues.extend(
                    _check_required_fields(item, item_schema, prefix=f"{prefix}[{index}].")
                )
    return issues


def validate_json_payload(payload: Any, schema_path: Path) -> list[str]:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    if not isinstance(schema, dict):
        return ["Invalid schema file"]
    return _check_required_fields(payload, schema)


def validate_jsonl_payload(text: str, schema_path: Path) -> list[str]:
    issues: list[str] = []
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return issues
    for index, line in enumerate(lines, start=1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            issues.append(f"line {index}: invalid JSON ({exc.msg})")
            continue
        row_issues = validate_json_payload(row, schema_path)
        issues.extend(f"line {index}: {msg}" for msg in row_issues)
    return issues


class TaskOutputValidator:
    def __init__(self, manager: TaskPromptManager) -> None:
        self.manager = manager

    def validate_artifact(
        self,
        *,
        task: TaskSpec,
        artifact: TaskArtifactSpec,
        path: Path,
    ) -> list[str]:
        if not artifact.schema:
            return []
        schema_path = self.manager.resolve_schema_path(task, artifact.schema)
        if schema_path is None:
            return [f"Schema not found: {artifact.schema}"]
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            return [f"Failed to read {path.name}: {exc}"]

        if artifact.format == "jsonl":
            return validate_jsonl_payload(raw, schema_path)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            return [f"Invalid JSON in {path.name}: {exc.msg}"]
        return validate_json_payload(payload, schema_path)
