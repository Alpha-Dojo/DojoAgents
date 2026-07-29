from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_json_schema(schema_path: Path) -> dict[str, Any] | None:
    try:
        raw = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return raw if isinstance(raw, dict) else None


def schema_skeleton(schema: dict[str, Any], *, depth: int = 0) -> Any:
    """Build a compact placeholder object from a JSON Schema (generic for any task)."""
    if depth > 6:
        return "..."

    if "const" in schema:
        return schema["const"]
    enum_values = schema.get("enum")
    if isinstance(enum_values, list) and enum_values:
        return enum_values[0]

    expected = schema.get("type")
    if isinstance(expected, list):
        expected = next((item for item in expected if isinstance(item, str)), None)

    if expected == "object" or "properties" in schema or "required" in schema:
        properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        required = [str(key) for key in (schema.get("required") or []) if str(key).strip()]
        keys = required or list(properties.keys())[:12]
        out: dict[str, Any] = {}
        for key in keys:
            sub = properties.get(key)
            out[key] = schema_skeleton(sub, depth=depth + 1) if isinstance(sub, dict) else f"<{key}>"
        return out

    if expected == "array" or "items" in schema:
        items = schema.get("items")
        if isinstance(items, dict):
            return [schema_skeleton(items, depth=depth + 1)]
        return []

    if expected == "string":
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and pattern.strip():
            return f"<string matching {pattern}>"
        return "<string>"
    if expected == "integer":
        return 0
    if expected == "number":
        return 0.0
    if expected == "boolean":
        return False
    if expected == "null":
        return None
    return "..."


def schema_write_notes(schema: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    if schema.get("additionalProperties") is False:
        notes.append("Top-level additionalProperties=false: do not add keys beyond the schema.")
    required = schema.get("required")
    if isinstance(required, list) and required:
        notes.append("Required top-level fields: " + ", ".join(f"`{key}`" for key in required))

    properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
    for key, sub in properties.items():
        if not isinstance(sub, dict):
            continue
        if sub.get("type") == "array":
            min_items = sub.get("minItems")
            max_items = sub.get("maxItems")
            bounds = []
            if isinstance(min_items, int):
                bounds.append(f"minItems={min_items}")
            if isinstance(max_items, int):
                bounds.append(f"maxItems={max_items}")
            if bounds:
                notes.append(f"`{key}` array constraints: {', '.join(bounds)}")
            contains = sub.get("contains")
            if isinstance(contains, dict):
                const = None
                props = contains.get("properties")
                if isinstance(props, dict):
                    type_schema = props.get("type")
                    if isinstance(type_schema, dict) and "const" in type_schema:
                        const = type_schema["const"]
                if const is not None:
                    min_c = sub.get("minContains", 1)
                    max_c = sub.get("maxContains")
                    note = f"`{key}` must contain exactly-matching item with type={const!r}"
                    if isinstance(min_c, int) and isinstance(max_c, int) and min_c == max_c == 1:
                        note = f"`{key}` must contain exactly 1 item with type={const!r}"
                    notes.append(note)
            items = sub.get("items")
            if isinstance(items, dict):
                enum_values = None
                item_props = items.get("properties") if isinstance(items.get("properties"), dict) else {}
                type_field = item_props.get("type")
                if isinstance(type_field, dict) and isinstance(type_field.get("enum"), list):
                    enum_values = type_field["enum"]
                if enum_values:
                    notes.append(f"`{key}[].type` enum: {enum_values}")
                if items.get("additionalProperties") is False:
                    notes.append(f"`{key}` items: additionalProperties=false")
        enum_values = sub.get("enum")
        if isinstance(enum_values, list) and enum_values:
            notes.append(f"`{key}` enum: {enum_values}")
    return notes


def format_write_contract_block(
    *,
    filename: str,
    fmt: str,
    schema: dict[str, Any] | None,
) -> list[str]:
    lines = [
        "Write contract (first successful write should match this — do not guess fields):",
        "- Tool: `write_session_file`",
        f"- filename: `{filename}`",
        f"- format: `{fmt}`",
    ]
    if schema is None:
        lines.append("- content: follow the TASK.md output example exactly")
        return lines

    skeleton = schema_skeleton(schema)
    lines.append("- content MUST validate against the task output schema. Skeleton:")
    lines.append("```json")
    lines.append(json.dumps(skeleton, ensure_ascii=False, indent=2))
    lines.append("```")
    for note in schema_write_notes(schema):
        lines.append(f"- {note}")
    return lines


def compact_schema_hint(schema: dict[str, Any] | None) -> str:
    if schema is None:
        return '{"...":"see TASK.md output example"}'
    try:
        return json.dumps(schema_skeleton(schema), ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        required = schema.get("required")
        if isinstance(required, list) and required:
            return "{" + ", ".join(f'"{key}":...' for key in required) + "}"
        return '{"...":"see TASK.md output example"}'
