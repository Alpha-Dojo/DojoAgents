from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dojoagents.sessions.identifiers import validate_output_filename, validate_session_id
from dojoagents.tools.write_authorization import (
    active_task_metadata,
    classify_write_session_file,
    preview_write_content,
    should_allow_write_session_file_for_task,
    write_session_file_guardrail_from_classification,
)
from dojoagents.sessions.atomic import _atomic_write_text
from dojoagents.tasks.manager import TaskPromptManager
from dojoagents.tasks.output_paths import resolve_task_read_path, resolve_task_write_path
from dojoagents.tasks.output_validation import find_output_artifact, validate_task_output_content
from dojoagents.tools.process_registry import (
    active_session_id,
    active_session_principal,
    active_write_session_file_guard,
)
from dojoagents.tools.registry import ToolSpec

SESSION_OUTPUT_SUBDIR = "outputs"
_SUPPORTED_FORMATS = frozenset({"text", "json", "jsonl"})


def resolve_session_output_dir(sessions_root: str | Path, session_id: str) -> Path:
    safe_session = validate_session_id(session_id)
    root = Path(sessions_root).expanduser().resolve()
    return root / safe_session / SESSION_OUTPUT_SUBDIR


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


def read_session_output(
    *,
    sessions_root: str | Path,
    session_id: str,
    filename: str,
    task_output_root: str | Path | None = None,
    request_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not str(session_id or "").strip():
        raise ValueError("session_id is required to read session output files")

    safe_name = validate_output_filename(filename)
    target_path: Path | None = None
    storage_kind = "session"
    if task_output_root is not None:
        target_path = resolve_task_read_path(
            task_output_root=task_output_root,
            request_metadata=request_metadata,
            filename=safe_name,
        )
        if target_path is not None:
            storage_kind = "task"

    if target_path is None:
        target_path = resolve_session_output_dir(sessions_root, session_id) / safe_name

    if not target_path.is_file():
        raise FileNotFoundError(f"session output file not found: {safe_name}")

    raw = target_path.read_text(encoding="utf-8")
    parsed: Any = raw
    if safe_name.endswith(".json"):
        parsed = json.loads(raw)
    elif safe_name.endswith(".jsonl"):
        parsed = [json.loads(line) for line in raw.splitlines() if line.strip()]

    return {
        "ok": True,
        "session_id": validate_session_id(session_id),
        "filename": safe_name,
        "path": str(target_path.resolve()),
        "storage_kind": storage_kind,
        "bytes_read": target_path.stat().st_size,
        "data": parsed,
        "content": raw,
    }


def get_read_session_output_spec(
    sessions_root: str | Path,
    *,
    task_output_root: str | Path | None = None,
    session_service: Any | None = None,
) -> ToolSpec:
    root = Path(sessions_root).expanduser().resolve()
    task_root = Path(task_output_root).expanduser().resolve() if task_output_root else None

    async def _handler(args: dict[str, Any]) -> dict[str, Any]:
        session_id = str(active_session_id.get() or args.get("session_id") or "").strip()
        if not session_id:
            raise RuntimeError("read_session_output requires an active agent session_id")
        guard_ctx = active_write_session_file_guard.get()
        request_metadata = guard_ctx.request_metadata if guard_ctx is not None else None
        filename = validate_output_filename(str(args.get("filename") or ""))
        if session_service is not None:
            principal = active_session_principal.get()
            if principal is None:
                raise RuntimeError("read_session_output requires an active session principal")
            record, raw_bytes = await session_service.read_named_object(principal, session_id, kind="output", name=filename)
            raw = raw_bytes.decode("utf-8")
            parsed: Any = raw
            if filename.endswith(".json"):
                parsed = json.loads(raw)
            elif filename.endswith(".jsonl"):
                parsed = [json.loads(line) for line in raw.splitlines() if line.strip()]
            payload = {
                "ok": True,
                "session_id": session_id,
                "filename": filename,
                "object_id": record.object_id,
                "storage_kind": "session_object",
                "bytes_read": len(raw_bytes),
                "data": parsed,
                "content": raw,
            }
        else:
            payload = read_session_output(
                sessions_root=root,
                session_id=session_id,
                filename=filename,
                task_output_root=task_root,
                request_metadata=request_metadata,
            )
        return {
            "content": json.dumps(payload, ensure_ascii=False, indent=2),
            "data": payload,
            "metadata": {
                "ok": True,
                "filename": payload["filename"],
                "path": payload.get("path"),
                "object_id": payload.get("object_id"),
            },
        }

    return ToolSpec(
        name="read_session_output",
        description=(
            "Read a previously written session output file from the current session outputs directory. "
            "Use before synthesis tasks that consume files written by write_session_file."
        ),
        parameters={
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Basename only, e.g. analysis_output.json",
                },
            },
            "required": ["filename"],
        },
        handler=_handler,
    )


def write_session_file(
    *,
    sessions_root: str | Path,
    session_id: str,
    filename: str,
    content: Any,
    fmt: str = "text",
    append: bool = False,
    task_output_root: str | Path | None = None,
    request_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not str(session_id or "").strip():
        raise ValueError("session_id is required to write session output files")

    safe_name = validate_output_filename(filename)
    normalized_fmt = str(fmt or "text").strip().lower() or "text"
    serialized = _serialize_content(content, normalized_fmt)

    storage_kind = "session"
    target_path: Path | None = None
    if task_output_root is not None:
        target_path = resolve_task_write_path(
            task_output_root=task_output_root,
            request_metadata=request_metadata,
            filename=safe_name,
        )
        if target_path is not None:
            storage_kind = "task"

    if target_path is None:
        output_dir = resolve_session_output_dir(sessions_root, session_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        target_path = output_dir / safe_name
    else:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        output_dir = target_path.parent

    if append and target_path.exists():
        existing = target_path.read_text(encoding="utf-8")
        if existing and not existing.endswith("\n") and serialized:
            existing += "\n"
        serialized = existing + serialized

    _atomic_write_text(target_path, serialized)
    bytes_written = target_path.stat().st_size
    return {
        "ok": True,
        "session_id": validate_session_id(session_id),
        "filename": safe_name,
        "format": normalized_fmt,
        "path": str(target_path),
        "output_dir": str(output_dir),
        "storage_kind": storage_kind,
        "bytes_written": bytes_written,
        "append": bool(append),
        "message": (f"Wrote {bytes_written} bytes to {target_path}. " "Use this exact path in your reply to the user."),
    }


def get_write_session_file_spec(
    sessions_root: str | Path,
    *,
    task_output_root: str | Path | None = None,
    task_manager: TaskPromptManager | None = None,
    session_service: Any | None = None,
) -> ToolSpec:
    root = Path(sessions_root).expanduser().resolve()
    task_root = Path(task_output_root).expanduser().resolve() if task_output_root else None

    async def _handler(args: dict[str, Any]) -> dict[str, Any]:
        session_id = str(active_session_id.get() or args.get("session_id") or "").strip()
        if not session_id:
            raise RuntimeError("write_session_file requires an active agent session_id")

        guard_ctx = active_write_session_file_guard.get()
        if guard_ctx is not None and guard_ctx.enabled:
            filename = str(args.get("filename") or "")
            if not should_allow_write_session_file_for_task(guard_ctx.request_metadata, filename=filename):
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

            active = active_task_metadata(guard_ctx.request_metadata if guard_ctx is not None else None)
            if active is not None and task_manager is not None:
                filename = str(args.get("filename") or "")
                artifact_meta = find_output_artifact(active, filename)
                if artifact_meta is not None:
                    fmt = str(args.get("format") or artifact_meta.get("format") or "json")
                    issues = validate_task_output_content(
                        manager=task_manager,
                        task_id=str(active.get("task_id") or ""),
                        artifact_meta=artifact_meta,
                        content=args.get("content"),
                        fmt=fmt,
                    )
                    if issues:
                        raise RuntimeError("Task output validation failed for " f"{filename}: {'; '.join(issues)}")

        if session_service is not None:
            if bool(args.get("append", False)):
                raise RuntimeError("append is unavailable for immutable session objects")
            principal = active_session_principal.get()
            if principal is None:
                raise RuntimeError("write_session_file requires an active session principal")
            filename = validate_output_filename(str(args.get("filename") or ""))
            fmt = str(args.get("format") or "text")
            serialized = _serialize_content(args.get("content"), fmt)
            content_type = {
                "json": "application/json",
                "jsonl": "application/x-ndjson",
                "text": "text/plain",
            }.get(fmt, "text/plain")
            record = await session_service.write_named_object(
                principal,
                session_id,
                kind="output",
                name=filename,
                content_type=content_type,
                data=serialized.encode("utf-8"),
                metadata={"format": fmt},
            )
            payload = {
                "ok": True,
                "session_id": session_id,
                "filename": filename,
                "format": fmt,
                "object_id": record.object_id,
                "storage_kind": "session_object",
                "bytes_written": len(serialized.encode("utf-8")),
                "append": False,
                "message": f"Wrote session object {record.object_id}.",
            }
        else:
            payload = write_session_file(
                sessions_root=root,
                session_id=session_id,
                filename=str(args.get("filename") or ""),
                content=args.get("content"),
                fmt=str(args.get("format") or "text"),
                append=bool(args.get("append", False)),
                task_output_root=task_root,
                request_metadata=guard_ctx.request_metadata if guard_ctx is not None else None,
            )
        return {
            "content": json.dumps(payload, ensure_ascii=False, indent=2),
            "data": payload,
            "metadata": {
                "ok": True,
                "path": payload.get("path"),
                "output_dir": payload.get("output_dir"),
                "object_id": payload.get("object_id"),
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
