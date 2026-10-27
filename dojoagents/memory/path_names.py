"""Stable, filesystem-safe names for session-owned memory artifacts."""

from __future__ import annotations

import hashlib
import re


SESSION_PATH_COMPONENT_MAX_LENGTH = 80
SESSION_HASH_LENGTH = 12


def slug_session_id(value: str, *, fallback: str = "session") -> str:
    """Return an ASCII path-component slug without separators or traversal."""

    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-").lower()
    return slug or fallback


def bounded_session_name(
    session_id: str,
    *,
    prefix: str,
    suffix: str = "",
    max_length: int = SESSION_PATH_COMPONENT_MAX_LENGTH,
) -> str:
    """Build a stable path component, hashing only when truncation is needed.

    Keeping short names unchanged preserves existing on-disk data.  Long names
    retain a readable prefix and receive a deterministic digest so two session
    IDs with the same truncated prefix cannot collide.
    """

    raw_session_id = session_id.strip() or "session"
    slug = slug_session_id(raw_session_id)
    candidate = f"{prefix}{slug}{suffix}"
    if len(candidate) <= max_length:
        return candidate

    digest = hashlib.sha256(raw_session_id.encode("utf-8")).hexdigest()[:SESSION_HASH_LENGTH]
    readable_budget = max_length - len(prefix) - len(suffix) - len("-") - len(digest)
    if readable_budget <= 0:
        raise ValueError("max_length is too small for the requested session name format")
    readable_prefix = slug[:readable_budget].rstrip("._-") or "session"
    return f"{prefix}{readable_prefix}-{digest}{suffix}"


__all__ = [
    "SESSION_HASH_LENGTH",
    "SESSION_PATH_COMPONENT_MAX_LENGTH",
    "bounded_session_name",
    "slug_session_id",
]
