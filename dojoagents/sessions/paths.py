"""Validated filesystem paths used by file-backed session adapters."""

from __future__ import annotations

from pathlib import Path

from dojoagents.sessions.identifiers import validate_output_filename, validate_session_id

SESSION_INPUT_SUBDIR = "inputs"


def resolve_session_input_dir(sessions_root: str | Path, session_id: str) -> Path:
    root = Path(sessions_root).expanduser().resolve()
    return root / validate_session_id(session_id) / SESSION_INPUT_SUBDIR


def resolve_session_input_file(
    sessions_root: str | Path,
    session_id: str,
    filename: str,
) -> Path:
    input_dir = resolve_session_input_dir(sessions_root, session_id).resolve()
    target = (input_dir / validate_output_filename(filename)).resolve()
    if target.parent != input_dir:
        raise ValueError(f"invalid input path for filename: {filename!r}")
    return target


__all__ = [
    "SESSION_INPUT_SUBDIR",
    "resolve_session_input_dir",
    "resolve_session_input_file",
]
