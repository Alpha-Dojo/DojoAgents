from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from dojoagents.agent.tool_result_artifacts import _validate_session_id
from dojoagents.agent.write_session_file_guardrails import (
    classify_write_session_file,
    preview_write_content,
    write_session_file_guardrail_from_classification,
)
from dojoagents.dashboard.services.file_store_base import _atomic_write_text
from dojoagents.tools.process_registry import active_session_id, active_write_session_file_guard
from dojoagents.tools.registry import ToolSpec

SESSION_OUTPUT_SUBDIR = "outputs"
_FILENAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SUPPORTED_FORMATS = frozenset({"text", "json", "jsonl"})


def resolve_session_output_dir(sessions_root: str | Path, session_id: str) -> Path:
    safe_session = _validate_session_id(session_id)
    root = Path(sessions_root).expanduser().resolve()
    return root / safe_session / SESSION_OUTPUT_SUBDIR


def validate_output_filename(filename: str) -> str:
    name = str(filename or "").strip()
    if not name:
        raise ValueError("filename is required")
    if "/" in name or "\\" in name or name in {".", ".."}:
        raise ValueError(f"filename must be a basename without directories: {filename!r}")
    if not _FILENAME_PATTERN.fullmatch(name):
        raise ValueError(
            f"invalid filename {filename!r}; use letters, numbers, '.', '-', '_' only"
        )
    return name


def _serialize_content(content: Any, fmt: str) -> str:
    normalized_fmt = str(fmt or "text").strip().lower() or "text"
    if normalized_fmt not in _SUPPORTED_FORMATS:
        raise ValueError(f"unsupported format {fmt!r}; expected text, json, or jsonl")

    if normalized_fmt == "text":
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        return str(content)

    if normalized_fmt == "json":
        if isinstance(content, str):
            text = content.strip()
            if text:
                json.loads(text)
            return content
        return json.dumps(content, ensure_ascii=False, indent=2)

    if isinstance(content, list):
        lines = [json.dumps(item, ensure_ascii=False, separators=(",", ":")) for item in content]
        return "\n".join(lines) + ("\n" if lines else "")
    if isinstance(content, str):
        text = content.strip()
        if not text:
            return ""
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            json.loads(line)
        if not text.endswith("\n"):
            text += "\n"
        return text
    return json.dumps(content, ensure_ascii=False, separators=(",", ":")) + "\n"


def write_session_file(
    *,
    sessions_root: str | Path,
    session_id: str,
    filename: str,
    content: Any,
    fmt: str = "text",
    append: bool = False,
) -> dict[str, Any]:
    if not str(session_id or "").strip():
        raise ValueError("session_id is required to write session output files")

    safe_name = validate_output_filename(filename)
    normalized_fmt = str(fmt or "text").strip().lower() or "text"
    serialized = _serialize_content(content, normalized_fmt)
    output_dir = resolve_session_output_dir(sessions_root, session_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / safe_name

    if append and target_path.exists():
        existing = target_path.read_text(encoding="utf-8")
        if existing and not existing.endswith("\n") and serialized:
            existing += "\n"
        serialized = existing + serialized

    _atomic_write_text(target_path, serialized)
    bytes_written = target_path.stat().st_size
    return {
        "ok": True,
        "session_id": _validate_session_id(session_id),
        "filename": safe_name,
        "format": normalized_fmt,
        "path": str(target_path),
        "output_dir": str(output_dir),
        "bytes_written": bytes_written,
        "append": bool(append),
        "message": (
            f"Wrote {bytes_written} bytes to {target_path}. "
            "Use this exact path in your reply to the user."
        ),
    }


def get_write_session_file_spec(sessions_root: str | Path) -> ToolSpec:
    root = Path(sessions_root).expanduser().resolve()

    async def _handler(args: dict[str, Any]) -> dict[str, Any]:
        session_id = str(active_session_id.get() or args.get("session_id") or "").strip()
        if not session_id:
            raise RuntimeError("write_session_file requires an active agent session_id")

        guard_ctx = active_write_session_file_guard.get()
        if guard_ctx is not None and guard_ctx.enabled:
            filename = str(args.get("filename") or "")
            content = args.get("content")
            classification = await classify_write_session_file(
                guard_ctx.user_message,
                guard_ctx.llm_provider,
                model=guard_ctx.model,
                request_metadata=guard_ctx.request_metadata,
                filename=filename,
                content_preview=preview_write_content(content),
                history=guard_ctx.history,
            )
            blocked, block_message, guardrail_code = write_session_file_guardrail_from_classification(
                "write_session_file",
                classification,
            )
            if blocked:
                raise RuntimeError(block_message)

        payload = write_session_file(
            sessions_root=root,
            session_id=session_id,
            filename=str(args.get("filename") or ""),
            content=args.get("content"),
            fmt=str(args.get("format") or "text"),
            append=bool(args.get("append", False)),
        )
        return {
            "content": json.dumps(payload, ensure_ascii=False, indent=2),
            "data": payload,
            "metadata": {
                "ok": True,
                "path": payload["path"],
                "output_dir": payload["output_dir"],
                "bytes_written": payload["bytes_written"],
            },
        }

    return ToolSpec(
        name="write_session_file",
        description=(
            "Write session output files ONLY when the user explicitly asked to save, export, "
            "or download a file. Returns absolute path and bytes_written. "
            "Do NOT use proactively for routine analysis — put results in the assistant reply. "
            "Also callable as dojo_tools.write_session_file(...) inside execute_code."
        ),
        parameters={
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Basename only, e.g. analysis.json or results.jsonl",
                },
                "content": {
                    "description": "String, JSON object/array, or JSONL row list depending on format",
                },
                "format": {
                    "type": "string",
                    "enum": ["text", "json", "jsonl"],
                    "description": "Serialization format (default: text)",
                },
                "append": {
                    "type": "boolean",
                    "description": "Append to an existing file instead of overwriting",
                    "default": False,
                },
            },
            "required": ["filename", "content"],
        },
        handler=_handler,
    )
