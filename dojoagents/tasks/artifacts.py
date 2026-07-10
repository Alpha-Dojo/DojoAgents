from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from dojoagents.tasks.models import TaskArtifactSpec, TaskSpec

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def resolve_dated_filename(base_filename: str, params: dict[str, Any] | None) -> str:
    """Insert trading_date into artifact basename: foo.json -> foo_2026-07-03.json."""
    name = str(base_filename or "").strip()
    if not name:
        return name
    trading_date = str((params or {}).get("trading_date") or "").strip()
    if not trading_date or not _DATE_RE.fullmatch(trading_date):
        return name

    path = Path(name)
    suffix = "".join(path.suffixes) or path.suffix
    stem = name[: -len(suffix)] if suffix else name
    if stem.endswith(f"_{trading_date}"):
        return name
    return f"{stem}_{trading_date}{suffix}"


def artifact_dicts_for_task(
    spec: TaskSpec,
    *,
    kind: str,
    params: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    items = spec.contract.inputs if kind == "input" else spec.contract.outputs
    resolved: list[dict[str, Any]] = []
    for item in items:
        resolved.append(
            {
                "filename": resolve_dated_filename(item.filename, params),
                "base_filename": item.filename,
                "format": item.format,
                "required": item.required,
                "schema": item.schema,
            }
        )
    return resolved


def resolve_artifact_filename(
    artifact: TaskArtifactSpec,
    params: dict[str, Any] | None,
) -> str:
    return resolve_dated_filename(artifact.filename, params)
