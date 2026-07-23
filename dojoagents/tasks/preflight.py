"""Domain-neutral parsing for optional pipeline preflight declarations."""

from __future__ import annotations

from typing import Any


def parse_pipeline_preflight(raw: object) -> dict[str, Any] | None:
    """Preserve Harness-owned preflight configuration without interpreting it."""

    if not isinstance(raw, dict) or not raw:
        return None
    return {str(key): value for key, value in raw.items()}


__all__ = ["parse_pipeline_preflight"]
