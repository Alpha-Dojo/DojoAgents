"""Domain-neutral persistence and projection contracts for large tool results."""

from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from dojoagents.logging import get_logger
from dojoagents.sessions.atomic import _atomic_write_json
from dojoagents.sessions.identifiers import validate_session_id

LOGGER = get_logger(__name__)

ARTIFACT_PERSIST_THRESHOLD_CHARS = 5000
ARTIFACT_KEEP_FULL_CONTENT_TOOLS = frozenset(
    {
        "execute_code",
        "code_execution",
        # File reads exist to put artifact bytes into the model turn; pointerizing
        # them requires execute_code + load_tool_result, which many task allowlists omit.
        "read_session_output",
    }
)
_CALL_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


class ToolResultArtifactAdapter(Protocol):
    """Optional Harness-owned interpretation of persisted tool results."""

    def extract_data(self, tool_name: str, content: str, data: Any) -> Any:
        """Return data to persist, optionally extracting it from textual content."""

    def build_pointer(
        self,
        *,
        tool_name: str,
        call_id: str,
        arguments: dict[str, Any] | None,
        data: Any,
        content: str | None,
    ) -> str:
        """Build the compact model-facing replacement for a persisted result."""

    def enrich_loaded_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Add Harness-specific metadata when an artifact is loaded in execute_code."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_tool_call_id(call_id: str) -> str:
    text = str(call_id or "").strip()
    if not text or not _CALL_ID_PATTERN.fullmatch(text):
        raise ValueError(f"invalid tool result call_id: {call_id!r}")
    return text


class ToolResultArtifactStore:
    """Persist large tool outputs for later loading by call ID."""

    def __init__(self, sessions_root: str | Path) -> None:
        self.sessions_root = Path(sessions_root).expanduser().resolve()

    def _artifact_dir(self, session_id: str) -> Path:
        return self.sessions_root / validate_session_id(session_id) / "tool_results"

    def artifact_path(self, session_id: str, call_id: str) -> Path:
        return self._artifact_dir(session_id) / f"{validate_tool_call_id(call_id)}.json"

    def save(
        self,
        *,
        session_id: str,
        call_id: str,
        tool_name: str,
        arguments: dict[str, Any] | None,
        content: str,
        data: Any = None,
        ok: bool = True,
        truncated: bool = False,
        error: str = "",
    ) -> Path:
        path = self.artifact_path(session_id, call_id)
        payload = {
            "schema_version": 1,
            "session_id": validate_session_id(session_id),
            "call_id": validate_tool_call_id(call_id),
            "tool_name": tool_name,
            "arguments": dict(arguments or {}),
            "ok": ok,
            "truncated": truncated,
            "error": str(error or ""),
            "content": content,
            "data": data,
            "created_at": _utc_now(),
        }
        _atomic_write_json(path, payload)
        return path

    def load(self, session_id: str, call_id: str) -> dict[str, Any] | None:
        path = self.artifact_path(session_id, call_id)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            LOGGER.exception("Failed to read tool result artifact: %s", path)
            return None
        return payload if isinstance(payload, dict) else None

    def list_summaries(self, session_id: str) -> list[dict[str, Any]]:
        directory = self._artifact_dir(session_id)
        if not directory.exists():
            return []
        rows: list[dict[str, Any]] = []
        for path in sorted(directory.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                LOGGER.exception("Failed to read tool result artifact summary: %s", path)
                continue
            if not isinstance(payload, dict):
                continue
            rows.append(
                {
                    "call_id": payload.get("call_id") or path.stem,
                    "tool_name": payload.get("tool_name"),
                    "created_at": payload.get("created_at"),
                    "truncated": bool(payload.get("truncated")),
                    "content_chars": len(str(payload.get("content") or "")),
                }
            )
        rows.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return rows


ARTIFACT_MAX_CONTENT_CHARS = 2_000_000
_PREVIEW_PRIORITY = (
    "schema_version",
    "partial",
    "warnings",
    "as_of",
    "window",
    "market",
    "markets_requested",
    "total_num",
    "count",
    "summary",
    "input_symbols",
    "input_tickers",
    "symbols",
    "tickers",
    "resolved",
    "resolved_symbol",
    "portfolio_id",
    "account_id",
    "rank",
    "sector_path_id",
    "name",
    "symbol",
    "d",
    "datetime",
    "last_price",
    "chg_pct",
    "close",
    "c",
    "items",
    "results",
    "quote",
    "bars_by_ticker",
    "bars",
    "klines",
    "us",
    "cn",
    "hk",
    "data",
    "performance",
    "orders",
    "holdings",
    "markets",
)
_PRIVATE_PREVIEW_KEYS = frozenset({"authorization", "api_key", "token", "secret", "password", "headers", "default_headers", "user_id", "account_id_token"})
_SERIES_KEYS = frozenset({"bars", "klines", "recent", "points", "series"})


def structured_artifact_data(data: Any, content: str | None) -> dict[str, Any] | list[Any] | None:
    """Use the actual result data, or a complete JSON content body."""
    if isinstance(data, (dict, list)):
        return data
    try:
        parsed = json.loads(content or "")
    except (TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, (dict, list)) else None


def compact_artifact_schema_hint(hint: dict[str, Any] | None, data: dict[str, Any] | list[Any]) -> dict[str, Any]:
    """Keep enough of an existing hint to explain the full result shape."""
    source = hint or {}
    compact = {key: source[key] for key in ("shape", "rows_key", "default_table") if source.get(key)}
    if "rows_key" not in compact and compact.get("default_table"):
        compact["rows_key"] = compact["default_table"]
    keys = source.get("top_level_keys")
    if isinstance(keys, list):
        compact["top_level_keys"] = [str(key) for key in keys[:24]]
    elif isinstance(data, dict):
        compact["top_level_keys"] = list(data)[:24]
    else:
        compact["shape"] = "list"
    for key in ("row_fields", "tree_keys"):
        values = source.get(key)
        if isinstance(values, list):
            compact[key] = values[:12]
    tables = source.get("tables")
    if isinstance(tables, dict):
        compact["tables"] = {
            name: {field: table[field] for field in ("path", "type", "row_fields") if field in table} for name, table in list(tables.items())[:6] if isinstance(table, dict)
        }
        for table in compact["tables"].values():
            if isinstance(table.get("row_fields"), list):
                table["row_fields"] = table["row_fields"][:12]
    return compact or {"shape": "object" if isinstance(data, dict) else "list"}


def build_artifact_data_preview(data: dict[str, Any] | list[Any], *, max_chars: int = 2200) -> tuple[Any, dict[str, Any]] | None:
    """Project actual values from known result shapes without slicing serialized JSON."""
    for row_limit, group_limit, text_limit in ((2, 8, 160), (1, 6, 100), (1, 4, 60)):
        total_rows: dict[str, int] = {}
        included_rows: dict[str, int] = {}
        omitted = False

        def project(value: Any, path: str, depth: int) -> Any:
            nonlocal omitted
            if depth > 6:
                omitted = True
                return None
            if isinstance(value, dict):
                keys = [key for key in value if str(key).lower() not in _PRIVATE_PREVIEW_KEYS]
                if len(keys) != len(value):
                    omitted = True
                order = {name: index for index, name in enumerate(_PREVIEW_PRIORITY)}
                keys.sort(key=lambda key: order.get(str(key), len(order)))
                if len(keys) > group_limit:
                    omitted = True
                return {str(key): project(value[key], f"{path}.{key}" if path else str(key), depth + 1) for key in keys[:group_limit]}
            if isinstance(value, list):
                total_rows[path or "items"] = len(value)
                if path.rsplit(".", 1)[-1] in _SERIES_KEYS or "bars_by_ticker." in path:
                    selected = value[-1:] if value else []
                else:
                    selected = value[: (8 if all(not isinstance(row, (dict, list)) for row in value[:8]) else row_limit)]
                included_rows[path or "items"] = len(selected)
                if len(selected) != len(value):
                    omitted = True
                return [project(row, f"{path}[{index}]", depth + 1) for index, row in enumerate(selected)]
            if isinstance(value, str) and len(value) > text_limit:
                omitted = True
                return value[:text_limit] + "…"
            if isinstance(value, float) and not math.isfinite(value):
                omitted = True
                return None
            if value is None or isinstance(value, (str, int, float, bool)):
                return value
            omitted = True
            return str(value)[:text_limit]

        preview = project(data, "", 0)
        if len(json.dumps(preview, ensure_ascii=False, default=str)) <= max_chars:
            return preview, {
                "complete": not omitted,
                "total_rows": total_rows,
                "included_rows": included_rows,
            }
    return None


def serialize_artifact_pointer(pointer: dict[str, Any], source: dict[str, Any] | list[Any], *, max_chars: int = 4000) -> str:
    """Bound the complete model-facing envelope while keeping values and load instructions."""

    def render() -> str:
        return json.dumps(pointer, ensure_ascii=False, separators=(",", ":"), allow_nan=False)

    message = render()
    if len(message) <= max_chars:
        return message
    notes = pointer.get("usage_notes")
    if isinstance(notes, str) and len(notes) > 600:
        pointer["usage_notes"] = notes[:600].rsplit(" ", 1)[0].rstrip() + "…"
        message = render()
    for field in ("pandas_example", "rpc_hint", "viz_build_hint"):
        if len(message) <= max_chars:
            return message
        pointer.pop(field, None)
        message = render()
    brief = pointer.get("structure_brief")
    if len(message) > max_chars and isinstance(brief, dict):
        brief.pop("how_to_read", None)
        message = render()
    if len(message) <= max_chars:
        return message
    for preview_chars in (1500, 1000, 600, 300):
        projected = build_artifact_data_preview(source, max_chars=preview_chars)
        if projected is None:
            continue
        pointer["data_preview"], pointer["preview_meta"] = projected
        message = render()
        if len(message) <= max_chars:
            return message
    raise ValueError("artifact pointer envelope exceeds the size limit")


def build_artifact_pointer_message(
    *,
    tool_name: str,
    call_id: str,
    arguments: dict[str, Any] | None = None,
    data: Any = None,
    content: str | None = None,
) -> str:
    """Build a model-facing JSON pointer with a bounded structured preview."""
    source = structured_artifact_data(data, content)
    if source is None:
        raise ValueError("structured artifact data is required for a pointer")
    projected = build_artifact_data_preview(source)
    if projected is None:
        raise ValueError("structured artifact preview exceeds the size limit")
    preview, preview_meta = projected
    pointer: dict[str, Any] = {
        "ok": True,
        "artifact": True,
        "delivery": "artifact",
        "tool": tool_name,
        "tool_name": tool_name,
        "call_id": call_id,
        "load_hint": f'dojo_tools.load_tool_result("{call_id}")',
        "artifact_ref": {"call_id": call_id, "copy_policy": "exact"},
        "data_preview": preview,
        "preview_meta": preview_meta,
        "schema_hint": compact_artifact_schema_hint(None, source),
        "description": "Structured preview of the saved result; load the full result only when omitted rows or fields are needed.",
    }
    compact_arguments = {
        str(key): value
        for key, value in dict(arguments or {}).items()
        if isinstance(value, (str, int, float, bool)) and value not in ("", None) and (not isinstance(value, str) or len(value) <= 120)
    }
    if compact_arguments:
        pointer["arguments"] = compact_arguments
    if isinstance(source, list):
        pointer["row_count"] = len(source)
    else:
        for key in ("items", "rows", "bars", "klines"):
            if isinstance(source.get(key), list):
                pointer["row_count"] = len(source[key])
                break
    return serialize_artifact_pointer(pointer, source)


__all__ = [
    "ARTIFACT_KEEP_FULL_CONTENT_TOOLS",
    "ARTIFACT_MAX_CONTENT_CHARS",
    "build_artifact_data_preview",
    "compact_artifact_schema_hint",
    "structured_artifact_data",
    "serialize_artifact_pointer",
    "ARTIFACT_PERSIST_THRESHOLD_CHARS",
    "ToolResultArtifactAdapter",
    "ToolResultArtifactStore",
    "build_artifact_pointer_message",
    "validate_session_id",
    "validate_tool_call_id",
]
