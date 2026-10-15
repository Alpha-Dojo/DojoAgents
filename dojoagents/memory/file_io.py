"""Async filesystem helpers for built-in memory providers."""

from __future__ import annotations

import uuid
from pathlib import Path

import anyio


async def read_text_if_present(path: Path) -> str:
    """Read UTF-8 text, returning an empty string for a missing file."""

    try:
        return await anyio.Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


async def atomic_write_text(path: Path, content: str) -> None:
    """Atomically replace a UTF-8 text file using async filesystem calls."""

    target = anyio.Path(path)
    await target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    try:
        await temporary.write_text(content, encoding="utf-8")
        await temporary.replace(target)
    finally:
        await temporary.unlink(missing_ok=True)


__all__ = ["atomic_write_text", "read_text_if_present"]
