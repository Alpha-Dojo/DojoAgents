from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dojoagents.agent.tool_result_artifacts import _validate_session_id
from dojoagents.dashboard.services.file_store_base import _atomic_write_bytes
from dojoagents.dashboard.services.session_input_ingest import (
    MAX_UPLOAD_BYTES,
    SUPPORTED_UPLOAD_EXTENSIONS,
    ingest_session_input_preview,
)
from dojoagents.dashboard.services.session_outputs import reveal_path_in_file_manager
from dojoagents.tools.session_file_names import validate_output_filename

SESSION_INPUT_SUBDIR = "inputs"


def resolve_session_input_dir(sessions_root: str | Path, session_id: str) -> Path:
    safe_session = _validate_session_id(session_id)
    root = Path(sessions_root).expanduser().resolve()
    return root / safe_session / SESSION_INPUT_SUBDIR


def resolve_session_input_file(
    sessions_root: str | Path,
    session_id: str,
    filename: str,
) -> Path:
    safe_session = _validate_session_id(session_id)
    safe_name = validate_output_filename(filename)
    input_dir = resolve_session_input_dir(sessions_root, safe_session).resolve()
    target = (input_dir / safe_name).resolve()
    if target.parent != input_dir:
        raise ValueError(f"invalid input path for filename: {filename!r}")
    return target


def validate_upload_filename(filename: str) -> str:
    safe_name = validate_output_filename(filename)
    suffix = Path(safe_name).suffix.lower()
    if suffix not in SUPPORTED_UPLOAD_EXTENSIONS:
        allowed = ", ".join(sorted(SUPPORTED_UPLOAD_EXTENSIONS))
        raise ValueError(f"unsupported file type {suffix or '(none)'}; allowed: {allowed}")
    return safe_name


def save_session_input_file(
    sessions_root: str | Path,
    session_id: str,
    filename: str,
    content: bytes,
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError(f"file exceeds upload limit of {MAX_UPLOAD_BYTES:,} bytes")
    if not content:
        raise ValueError("empty files cannot be uploaded")

    safe_name = validate_upload_filename(filename)
    input_dir = resolve_session_input_dir(sessions_root, session_id)
    input_dir.mkdir(parents=True, exist_ok=True)
    target = input_dir / safe_name
    if target.exists() and not overwrite:
        raise ValueError(f"input file already exists: {safe_name}")

    _atomic_write_bytes(target, content)
    preview = ingest_session_input_preview(target)
    preview["updated_at"] = datetime.fromtimestamp(target.stat().st_mtime, tz=timezone.utc).isoformat()
    return preview


def list_session_input_files(
    sessions_root: str | Path,
    session_id: str,
    *,
    include_preview: bool = True,
) -> dict[str, Any]:
    safe_session = _validate_session_id(session_id)
    input_dir = resolve_session_input_dir(sessions_root, safe_session)
    files: list[dict[str, Any]] = []
    if input_dir.is_dir():
        for path in sorted(input_dir.iterdir(), key=lambda item: item.name.lower()):
            if not path.is_file():
                continue
            stat = path.stat()
            item: dict[str, Any] = {
                "filename": path.name,
                "path": str(path.resolve()),
                "bytes": stat.st_size,
                "kind": detect_kind_from_name(path.name),
                "updated_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            }
            if include_preview:
                try:
                    preview = ingest_session_input_preview(path)
                    item.update(
                        {
                            "kind": preview.get("kind", item["kind"]),
                            "summary": preview.get("summary"),
                            "preview_text": preview.get("preview_text"),
                            "truncated": preview.get("truncated", False),
                        }
                    )
                except ValueError:
                    item["summary"] = f"binary file, {stat.st_size:,} bytes"
            files.append(item)
    return {
        "session_id": safe_session,
        "input_dir": str(input_dir.resolve()),
        "files": files,
    }


def detect_kind_from_name(filename: str) -> str:
    from dojoagents.dashboard.services.session_input_ingest import detect_session_input_kind

    return detect_session_input_kind(filename)


def reveal_session_input_file(path: Path) -> None:
    reveal_path_in_file_manager(path)
