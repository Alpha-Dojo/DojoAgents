from __future__ import annotations

import re

_FILENAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def validate_session_id(session_id: str) -> str:
    text = str(session_id or "").strip()
    if not text or "/" in text or "\\" in text or text in {".", ".."}:
        raise ValueError(f"invalid session id: {session_id!r}")
    return text


def validate_output_filename(filename: str) -> str:
    name = str(filename or "").strip()
    if not name:
        raise ValueError("filename is required")
    if "/" in name or "\\" in name or name in {".", ".."}:
        raise ValueError(f"filename must be a basename without directories: {filename!r}")
    if not _FILENAME_PATTERN.fullmatch(name):
        raise ValueError(f"invalid filename {filename!r}; use letters, numbers, '.', '-', '_' only")
    return name


__all__ = ["validate_output_filename", "validate_session_id"]
