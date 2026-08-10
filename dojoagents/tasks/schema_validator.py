from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from dojoagents.tasks.manager import TaskPromptManager
from dojoagents.tasks.models import TaskArtifactSpec, TaskSpec


class TaskSchemaValidationError(ValueError):
    pass


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return True


def _item_matches_schema(item: Any, schema: dict[str, Any]) -> bool:
    return not _validate_against_schema(item, schema, prefix="")


def _validate_against_schema(payload: Any, schema: dict[str, Any], *, prefix: str = "") -> list[str]:
    issues: list[str] = []
    expected_type = schema.get("type")
    if isinstance(expected_type, str) and not _matches_type(payload, expected_type):
        issues.append(f"{prefix}expected type {expected_type}, got {_type_name(payload)}")
        return issues
    if isinstance(expected_type, list):
        if not any(_matches_type(payload, item) for item in expected_type if isinstance(item, str)):
            issues.append(f"{prefix}expected type one of {expected_type}, got {_type_name(payload)}")
            return issues

    if "const" in schema and payload != schema["const"]:
        issues.append(f"{prefix}expected const {schema['const']!r}, got {payload!r}")

    enum_values = schema.get("enum")
    if isinstance(enum_values, list) and payload not in enum_values:
        issues.append(f"{prefix}invalid enum value {payload!r}; expected one of {enum_values}")

    pattern = schema.get("pattern")
    if pattern and isinstance(payload, str) and not re.fullmatch(pattern, payload):
        issues.append(f"{prefix}value does not match pattern {pattern}")

    min_length = schema.get("minLength")
    if isinstance(min_length, int) and isinstance(payload, str) and len(payload) < min_length:
        issues.append(f"{prefix}string shorter than minLength {min_length}")
    max_length = schema.get("maxLength")
    if isinstance(max_length, int) and isinstance(payload, str) and len(payload) > max_length:
        issues.append(f"{prefix}string longer than maxLength {max_length}")

    if isinstance(payload, dict) and (expected_type == "object" or expected_type is None or "properties" in schema):
        for key in schema.get("required") or []:
            if key not in payload:
                issues.append(f"{prefix}missing required field: {key}")

        properties = schema.get("properties") or {}
        if isinstance(properties, dict):
            for key, subschema in properties.items():
                if key in payload and isinstance(subschema, dict):
                    issues.extend(_validate_against_schema(payload[key], subschema, prefix=f"{prefix}{key}."))

        if schema.get("additionalProperties") is False:
            allowed = set(properties.keys()) if isinstance(properties, dict) else set()
            extras = [key for key in payload.keys() if key not in allowed]
            if extras:
                issues.append(f"{prefix}additional properties not allowed: {', '.join(sorted(map(str, extras)))}")

    if isinstance(payload, list) and (expected_type == "array" or "items" in schema or "contains" in schema):
        min_items = schema.get("minItems")
        if isinstance(min_items, int) and len(payload) < min_items:
            issues.append(f"{prefix}array shorter than minItems {min_items}")
        max_items = schema.get("maxItems")
        if isinstance(max_items, int) and len(payload) > max_items:
            issues.append(f"{prefix}array longer than maxItems {max_items}")

        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(payload):
                issues.extend(_validate_against_schema(item, item_schema, prefix=f"{prefix}[{index}]."))

        contains = schema.get("contains")
        if isinstance(contains, dict):
            match_count = sum(1 for item in payload if _item_matches_schema(item, contains))
            min_contains = schema.get("minContains", 1)
            max_contains = schema.get("maxContains")
            if isinstance(min_contains, int) and match_count < min_contains:
                issues.append(f"{prefix}array must contain at least {min_contains} matching item(s)")
            if isinstance(max_contains, int) and match_count > max_contains:
                issues.append(f"{prefix}array must contain at most {max_contains} matching item(s)")

    return issues


def validate_json_payload(payload: Any, schema_path: Path) -> list[str]:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    if not isinstance(schema, dict):
        return ["Invalid schema file"]
    return _validate_against_schema(payload, schema)


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
