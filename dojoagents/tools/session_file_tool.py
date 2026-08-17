from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dojoagents.sessions.atomic import _atomic_write_text
from dojoagents.sessions.identifiers import validate_output_filename, validate_session_id
from dojoagents.tasks.manager import TaskPromptManager
from dojoagents.tasks.output_paths import resolve_task_read_path, resolve_task_write_path
from dojoagents.tasks.output_validation import find_output_artifact, validate_task_output_content
from dojoagents.tools.process_registry import (
    active_session_id,
    active_session_principal,
    active_write_session_file_guard,
)
from dojoagents.tools.registry import ToolSpec
from dojoagents.tools.write_authorization import (
    active_task_metadata,
    classify_write_session_file,
    preview_write_content,
    should_allow_write_session_file_for_task,
    write_session_file_guardrail_from_classification,
)

SESSION_OUTPUT_SUBDIR = "outputs"
_SUPPORTED_FORMATS = frozenset({"text", "json", "jsonl"})
_READ_CONTENT_MAX_CHARS = 100_000
_FILE_LOCK_TIMEOUT_SECONDS = 30


def resolve_session_output_dir(sessions_root: str | Path, session_id: str) -> Path:
    safe_session = validate_session_id(session_id)
    root = Path(sessions_root).expanduser().resolve()
    return root / safe_session / SESSION_OUTPUT_SUBDIR


def _normalize_fmt(fmt: str | None) -> str:
    normalized = str(fmt or "text").strip().lower() or "text"
    if normalized not in _SUPPORTED_FORMATS:
        raise ValueError(f"unsupported format {fmt!r}; expected text, json, or jsonl")
    return normalized


def _validate_append(fmt: str, append: bool, *, allow_append: bool) -> None:
    if not append:
        return
    if not allow_append:
        raise ValueError(
            "append is only supported for filesystem outputs (active task or session outputs dir); "
            "session objects are immutable — rewrite with append=false"
        )
    if fmt == "json":
        raise ValueError("append is not supported for format=json; use format=jsonl or rewrite the full file")
    if fmt not in {"text", "jsonl"}:
        raise ValueError(f"append is only supported for text/jsonl, not {fmt!r}")


def _serialize_content(content: Any, fmt: str) -> str:
    normalized_fmt = _normalize_fmt(fmt)

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
        for line in text.splitlines():
            if not line.strip():
                continue
            json.loads(line)
        if not text.endswith("\n"):
            text += "\n"
        return text
    return json.dumps(content, ensure_ascii=False, separators=(",", ":")) + "\n"


def _infer_fmt(filename: str, fmt: str | None) -> str:
    if fmt:
        return _normalize_fmt(fmt)
    name = str(filename or "")
    if name.endswith(".jsonl"):
        return "jsonl"
    if name.endswith(".json"):
        return "json"
    return "text"


def _parse_payload(safe_name: str, raw: str, *, fmt: str | None = None) -> Any:
    kind = _infer_fmt(safe_name, fmt)
    if kind == "json":
        return json.loads(raw)
    if kind == "jsonl":
        return [json.loads(line) for line in raw.splitlines() if line.strip()]
    return raw


def _coerce_output_filename(filename: str) -> str:
    name = str(filename or "").strip()
    if "/" in name or "\\" in name:
        name = Path(name).name
    return validate_output_filename(name)


def _truncate_read_payload(payload: dict[str, Any], *, max_chars: int) -> dict[str, Any]:
    content = str(payload.get("content") or "")
    if max_chars <= 0 or len(content) <= max_chars:
        return payload
    out = dict(payload)
    out["content"] = content[:max_chars]
    out["data"] = None
    out["truncated"] = True
    out["content_chars"] = len(content)
    out["content_chars_returned"] = max_chars
    out["message"] = (
        f"Content truncated to {max_chars} of {len(content)} chars to protect the model context. "
        "Retry with a larger max_chars; do not shrink max_chars to probe the file."
    )
    return out


def _append_text_unlocked(path: Path, serialized: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    needs_nl = False
    if path.exists() and path.stat().st_size > 0:
        with path.open("rb") as raw:
            raw.seek(-1, 2)
            needs_nl = raw.read(1) != b"\n"
    with path.open("a", encoding="utf-8") as fh:
        if needs_nl and serialized:
            fh.write("\n")
        fh.write(serialized)


def _write_text_locked(path: Path, serialized: str, *, append: bool) -> None:
    """Append and overwrite share one companion lock so they cannot interleave.

    The ``.lock`` sidecar is removed after the lock is released so task output
    directories are not littered with leftover lock files.
    """
    import portalocker

    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    try:
        with portalocker.Lock(str(lock_path), mode="a+", timeout=_FILE_LOCK_TIMEOUT_SECONDS):
            if append:
                _append_text_unlocked(path, serialized)
            else:
                _atomic_write_text(path, serialized)
    finally:
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass


def _content_type_for(fmt: str) -> str:
    return {
        "json": "application/json",
        "jsonl": "application/x-ndjson",
        "text": "text/plain",
    }.get(fmt, "text/plain")


@dataclass
class SessionFileIO:
    """Resolve/read/write for session files and task artifacts.

    Active-task artifacts use the task filesystem only — they must not take the
    session-store lock that heartbeats and run events already contend on.
    Freeform (no active task) may still use session named objects.
    """

    sessions_root: Path
    task_output_root: Path | None = None
    session_service: Any | None = None

    @classmethod
    def create(
        cls,
        sessions_root: str | Path,
        *,
        task_output_root: str | Path | None = None,
        session_service: Any | None = None,
    ) -> "SessionFileIO":
        return cls(
            sessions_root=Path(sessions_root).expanduser().resolve(),
            task_output_root=(Path(task_output_root).expanduser().resolve() if task_output_root else None),
            session_service=session_service,
        )

    def resolve_write_path(
        self,
        *,
        session_id: str,
        filename: str,
        request_metadata: dict[str, Any] | None = None,
    ) -> tuple[Path, str]:
        """Return (path, storage_kind) for a filesystem write."""
        safe_name = validate_output_filename(filename)
        if self.task_output_root is not None:
            task_path = resolve_task_write_path(
                task_output_root=self.task_output_root,
                request_metadata=request_metadata,
                filename=safe_name,
            )
            if task_path is not None:
                return task_path, "task"
        output_dir = resolve_session_output_dir(self.sessions_root, session_id)
        return output_dir / safe_name, "session"

    def resolve_read_path(
        self,
        *,
        session_id: str,
        filename: str,
        request_metadata: dict[str, Any] | None = None,
    ) -> tuple[Path, str]:
        """Return (path, storage_kind) for a filesystem read."""
        safe_name = validate_output_filename(filename)
        if self.task_output_root is not None:
            task_path = resolve_task_read_path(
                task_output_root=self.task_output_root,
                request_metadata=request_metadata,
                filename=safe_name,
            )
            if task_path is not None and task_path.is_file():
                return task_path, "task"
            if task_path is not None:
                raise FileNotFoundError(f"session output file not found: {safe_name}")
        target = resolve_session_output_dir(self.sessions_root, session_id) / safe_name
        return target, "session"

    def read_filesystem(
        self,
        *,
        session_id: str,
        filename: str,
        request_metadata: dict[str, Any] | None = None,
        fmt: str | None = None,
        max_chars: int = _READ_CONTENT_MAX_CHARS,
    ) -> dict[str, Any]:
        if not str(session_id or "").strip():
            raise ValueError("session_id is required to read session output files")
        safe_name = _coerce_output_filename(filename)
        target_path, storage_kind = self.resolve_read_path(
            session_id=session_id,
            filename=safe_name,
            request_metadata=request_metadata,
        )
        if not target_path.is_file():
            raise FileNotFoundError(f"session output file not found: {safe_name}")
        raw = target_path.read_text(encoding="utf-8")
        payload = {
            "ok": True,
            "session_id": validate_session_id(session_id),
            "filename": safe_name,
            "path": str(target_path.resolve()),
            "storage_kind": storage_kind,
            "bytes_read": target_path.stat().st_size,
            "content": raw,
        }
        if max_chars > 0 and len(raw) > max_chars:
            payload["data"] = None
            return _truncate_read_payload(payload, max_chars=max_chars)
        payload["data"] = _parse_payload(safe_name, raw, fmt=fmt)
        return payload

    def write_filesystem(
        self,
        *,
        session_id: str,
        filename: str,
        content: Any,
        fmt: str = "text",
        append: bool = False,
        request_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not str(session_id or "").strip():
            raise ValueError("session_id is required to write session output files")
        safe_name = _coerce_output_filename(filename)
        normalized_fmt = _normalize_fmt(fmt)
        _validate_append(normalized_fmt, append, allow_append=True)
        serialized = _serialize_content(content, normalized_fmt)
        target_path, storage_kind = self.resolve_write_path(
            session_id=session_id,
            filename=safe_name,
            request_metadata=request_metadata,
        )
        _write_text_locked(target_path, serialized, append=append)
        bytes_written = target_path.stat().st_size
        return {
            "ok": True,
            "session_id": validate_session_id(session_id),
            "filename": safe_name,
            "format": normalized_fmt,
            "path": str(target_path),
            "output_dir": str(target_path.parent),
            "storage_kind": storage_kind,
            "bytes_written": bytes_written,
            "append": bool(append),
            "message": (
                f"Wrote {bytes_written} bytes to {target_path}. "
                f"You may tell the user this path. For read_session_output/write_session_file "
                f"pass basename only: {safe_name}"
            ),
        }

    async def read(
        self,
        *,
        session_id: str,
        filename: str,
        principal: Any | None = None,
        request_metadata: dict[str, Any] | None = None,
        fmt: str | None = None,
        max_chars: int = _READ_CONTENT_MAX_CHARS,
    ) -> dict[str, Any]:
        safe_name = _coerce_output_filename(filename)
        active = active_task_metadata(request_metadata)

        # Task artifacts: filesystem only (same truth as activator / pipeline handoff).
        if active is not None and self.task_output_root is not None:
            return await asyncio.to_thread(
                self.read_filesystem,
                session_id=session_id,
                filename=safe_name,
                request_metadata=request_metadata,
                fmt=fmt,
                max_chars=max_chars,
            )

        if self.session_service is not None:
            if principal is None:
                raise RuntimeError("read_session_output requires an active session principal")
            try:
                return await self._read_session_object(
                    principal,
                    session_id,
                    safe_name,
                    fmt=fmt,
                    max_chars=max_chars,
                )
            except Exception as exc:
                from dojoagents.sessions.errors import SessionNotFoundError

                if not isinstance(exc, SessionNotFoundError):
                    raise
                return await asyncio.to_thread(
                    self.read_filesystem,
                    session_id=session_id,
                    filename=safe_name,
                    request_metadata=request_metadata,
                    fmt=fmt,
                    max_chars=max_chars,
                )

        return await asyncio.to_thread(
            self.read_filesystem,
            session_id=session_id,
            filename=safe_name,
            request_metadata=request_metadata,
            fmt=fmt,
            max_chars=max_chars,
        )

    async def write(
        self,
        *,
        session_id: str,
        filename: str,
        content: Any,
        fmt: str = "text",
        append: bool = False,
        principal: Any | None = None,
        request_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        safe_name = _coerce_output_filename(filename)
        normalized_fmt = _normalize_fmt(fmt)
        active = active_task_metadata(request_metadata)
        filesystem_ok = (active is not None and self.task_output_root is not None) or self.session_service is None
        _validate_append(normalized_fmt, append, allow_append=filesystem_ok)

        # Task artifacts never touch the session-store lock used by heartbeats.
        if active is not None and self.task_output_root is not None:
            return await asyncio.to_thread(
                self.write_filesystem,
                session_id=session_id,
                filename=safe_name,
                content=content,
                fmt=normalized_fmt,
                append=append,
                request_metadata=request_metadata,
            )

        if self.session_service is not None:
            if principal is None:
                raise RuntimeError("write_session_file requires an active session principal")
            return await self._write_session_object(
                principal,
                session_id,
                safe_name,
                content=content,
                fmt=normalized_fmt,
            )

        return await asyncio.to_thread(
            self.write_filesystem,
            session_id=session_id,
            filename=safe_name,
            content=content,
            fmt=normalized_fmt,
            append=append,
            request_metadata=request_metadata,
        )

    async def _read_session_object(
        self,
        principal: Any,
        session_id: str,
        filename: str,
        *,
        fmt: str | None = None,
        max_chars: int = _READ_CONTENT_MAX_CHARS,
    ) -> dict[str, Any]:
        assert self.session_service is not None
        record, raw_bytes = await self.session_service.read_named_object(
            principal,
            session_id,
            kind="output",
            name=filename,
        )
        raw = raw_bytes.decode("utf-8")
        payload = {
            "ok": True,
            "session_id": session_id,
            "filename": filename,
            "object_id": record.object_id,
            "storage_kind": "session_object",
            "bytes_read": len(raw_bytes),
            "content": raw,
        }
        if max_chars > 0 and len(raw) > max_chars:
            payload["data"] = None
            return _truncate_read_payload(payload, max_chars=max_chars)
        payload["data"] = _parse_payload(filename, raw, fmt=fmt)
        return payload

    async def _write_session_object(
        self,
        principal: Any,
        session_id: str,
        filename: str,
        *,
        content: Any,
        fmt: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        assert self.session_service is not None
        serialized = _serialize_content(content, fmt)
        record = await self.session_service.write_named_object(
            principal,
            session_id,
            kind="output",
            name=filename,
            content_type=_content_type_for(fmt),
            data=serialized.encode("utf-8"),
            metadata=metadata or {"format": fmt},
        )
        return {
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


# --- Backward-compatible sync helpers (filesystem only) ---------------------


def read_session_output(
    *,
    sessions_root: str | Path,
    session_id: str,
    filename: str,
    task_output_root: str | Path | None = None,
    request_metadata: dict[str, Any] | None = None,
    fmt: str | None = None,
    max_chars: int = _READ_CONTENT_MAX_CHARS,
) -> dict[str, Any]:
    return SessionFileIO.create(sessions_root, task_output_root=task_output_root).read_filesystem(
        session_id=session_id,
        filename=filename,
        request_metadata=request_metadata,
        fmt=fmt,
        max_chars=max_chars,
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
    return SessionFileIO.create(sessions_root, task_output_root=task_output_root).write_filesystem(
        session_id=session_id,
        filename=filename,
        content=content,
        fmt=fmt,
        append=append,
        request_metadata=request_metadata,
    )


def _expected_payload_hint(
    task_manager: TaskPromptManager | None,
    active: dict[str, Any],
    artifact_meta: dict[str, Any],
) -> str:
    from dojoagents.tasks.write_contract import compact_schema_hint, load_json_schema

    task_id = str(active.get("task_id") or "")
    schema_ref = str(artifact_meta.get("schema") or "").strip()
    if task_manager is None or not schema_ref:
        return compact_schema_hint(None)
    spec = task_manager.get_task(task_id)
    if spec is None:
        return compact_schema_hint(None)
    schema_path = task_manager.resolve_schema_path(spec, schema_ref)
    if schema_path is None:
        return compact_schema_hint(None)
    return compact_schema_hint(load_json_schema(schema_path))


def _tool_result(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": json.dumps(payload, ensure_ascii=False, indent=2),
        "data": payload,
        "metadata": {
            "ok": True,
            "filename": payload.get("filename"),
            "path": payload.get("path"),
            "output_dir": payload.get("output_dir"),
            "object_id": payload.get("object_id"),
            "bytes_written": payload.get("bytes_written"),
            "bytes_read": payload.get("bytes_read"),
            "truncated": payload.get("truncated"),
        },
    }


def get_read_session_output_spec(
    sessions_root: str | Path,
    *,
    task_output_root: str | Path | None = None,
    session_service: Any | None = None,
) -> ToolSpec:
    io = SessionFileIO.create(
        sessions_root,
        task_output_root=task_output_root,
        session_service=session_service,
    )

    async def _handler(args: dict[str, Any]) -> dict[str, Any]:
        session_id = str(active_session_id.get() or args.get("session_id") or "").strip()
        if not session_id:
            raise RuntimeError("read_session_output requires an active agent session_id")
        guard_ctx = active_write_session_file_guard.get()
        request_metadata = guard_ctx.request_metadata if guard_ctx is not None else None
        max_chars_raw = args.get("max_chars", _READ_CONTENT_MAX_CHARS)
        try:
            max_chars = int(max_chars_raw)
        except (TypeError, ValueError):
            max_chars = _READ_CONTENT_MAX_CHARS
        payload = await io.read(
            session_id=session_id,
            filename=str(args.get("filename") or ""),
            principal=active_session_principal.get(),
            request_metadata=request_metadata,
            fmt=(str(args["format"]).strip().lower() if args.get("format") else None),
            max_chars=max_chars,
        )
        return _tool_result(payload)

    return ToolSpec(
        name="read_session_output",
        description=(
            "Read a previously written session/task output file by basename "
            "(absolute paths are accepted and reduced to the basename). "
            "In active task mode, reads upstream task artifacts from "
            "~/.dojo/tasks/outputs/{source_task}/ when present. "
            f"Default max_chars={_READ_CONTENT_MAX_CHARS} already covers typical packs — "
            "do not shrink max_chars to probe the file."
        ),
        parameters={
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Basename preferred, e.g. analysis_output.json (paths ok; basename used)",
                },
                "format": {
                    "type": "string",
                    "enum": ["text", "json", "jsonl"],
                    "description": "Optional parse hint; defaults from filename extension",
                },
                "max_chars": {
                    "type": "integer",
                    "description": (
                        f"Max characters returned in content (default {_READ_CONTENT_MAX_CHARS}). "
                        "Truncated reads set truncated=true and data=null. "
                        "Do not shrink max_chars to probe the file."
                    ),
                    "default": _READ_CONTENT_MAX_CHARS,
                },
            },
            "required": ["filename"],
        },
        handler=_handler,
    )


def get_write_session_file_spec(
    sessions_root: str | Path,
    *,
    task_output_root: str | Path | None = None,
    task_manager: TaskPromptManager | None = None,
    session_service: Any | None = None,
) -> ToolSpec:
    io = SessionFileIO.create(
        sessions_root,
        task_output_root=task_output_root,
        session_service=session_service,
    )

    async def _handler(args: dict[str, Any]) -> dict[str, Any]:
        session_id = str(active_session_id.get() or args.get("session_id") or "").strip()
        if not session_id:
            raise RuntimeError("write_session_file requires an active agent session_id")

        guard_ctx = active_write_session_file_guard.get()
        request_metadata = guard_ctx.request_metadata if guard_ctx is not None else None
        content = args.get("content")
        filename = str(args.get("filename") or "")
        active = active_task_metadata(request_metadata)
        artifact_meta = find_output_artifact(active, filename) if active is not None else None

        if guard_ctx is not None and guard_ctx.enabled:
            if not should_allow_write_session_file_for_task(request_metadata, filename=filename):
                classification = await classify_write_session_file(
                    guard_ctx.user_message,
                    guard_ctx.llm_provider,
                    model=guard_ctx.model,
                    request_metadata=request_metadata,
                    filename=filename,
                    content_preview=preview_write_content(content),
                    history=guard_ctx.history,
                )
                blocked, block_message, _guardrail_code = write_session_file_guardrail_from_classification(
                    "write_session_file",
                    classification,
                )
                if blocked:
                    raise RuntimeError(block_message)

            if active is not None and task_manager is not None and artifact_meta is not None:
                fmt = str(args.get("format") or artifact_meta.get("format") or "json")
                issues = validate_task_output_content(
                    manager=task_manager,
                    task_id=str(active.get("task_id") or ""),
                    artifact_meta=artifact_meta,
                    content=content,
                    fmt=fmt,
                )
                if issues:
                    example = _expected_payload_hint(task_manager, active, artifact_meta)
                    detail = "; ".join(issues)
                    raise RuntimeError(
                        f"Task output validation failed for {filename}: {detail}. "
                        f"Rewrite with format=json and EXACT shape: {example}"
                    )

        fmt = str(args.get("format") or (artifact_meta or {}).get("format") or "text")
        payload = await io.write(
            session_id=session_id,
            filename=filename,
            content=content,
            fmt=fmt,
            append=bool(args.get("append", False)),
            principal=active_session_principal.get(),
            request_metadata=request_metadata,
        )
        return _tool_result(payload)

    return ToolSpec(
        name="write_session_file",
        description=(
            "Write session/task output files. In active task mode, persists under "
            "~/.dojo/tasks/outputs/{task_id}/ using the exact required filename and schema. "
            "Returns absolute path and bytes_written. "
            "append=true is only for text/jsonl on filesystem outputs (not format=json, "
            "not immutable session objects). "
            "Also callable as dojo_tools.write_session_file(...) inside execute_code."
        ),
        parameters={
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Basename preferred, e.g. analysis.json (paths ok; basename used)",
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
                    "description": (
                        "Append for text/jsonl filesystem writes only. "
                        "Forbidden with format=json or session-object storage."
                    ),
                    "default": False,
                },
            },
            "required": ["filename", "content"],
        },
        handler=_handler,
    )
