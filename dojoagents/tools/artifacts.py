"""Domain-neutral persistence and projection contracts for large tool results."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from dojoagents.logging import get_logger
from dojoagents.sessions.atomic import _atomic_write_json
from dojoagents.sessions.identifiers import validate_session_id

LOGGER = get_logger(__name__)

ARTIFACT_PERSIST_THRESHOLD_CHARS = 5000
ARTIFACT_KEEP_FULL_CONTENT_TOOLS = frozenset({"execute_code", "code_execution"})
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


def build_artifact_pointer_message(
    *,
    tool_name: str,
    call_id: str,
    arguments: dict[str, Any] | None = None,
    data: Any = None,
    content: str | None = None,
) -> str:
    """Build a compact, domain-neutral pointer to a persisted tool result."""

    del content
    summary: dict[str, Any] = {
        "artifact": True,
        "tool": tool_name,
        "call_id": call_id,
        "load_hint": f'dojo_tools.load_tool_result("{call_id}")',
    }
    compact_arguments = {str(key): value for key, value in dict(arguments or {}).items() if isinstance(value, (str, int, float, bool)) and value not in ("", None)}
    if compact_arguments:
        summary["arguments"] = compact_arguments
    if isinstance(data, dict):
        for key in ("items", "rows"):
            value = data.get(key)
            if isinstance(value, list):
                summary["row_count"] = len(value)
                break
    return json.dumps(summary, ensure_ascii=False, indent=2)


__all__ = [
    "ARTIFACT_KEEP_FULL_CONTENT_TOOLS",
    "ARTIFACT_PERSIST_THRESHOLD_CHARS",
    "ToolResultArtifactAdapter",
    "ToolResultArtifactStore",
    "build_artifact_pointer_message",
    "validate_session_id",
    "validate_tool_call_id",
]
