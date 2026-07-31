from __future__ import annotations

import re
from typing import Any

from dojoagents.tasks.models import TaskArtifactSpec, TaskSpec

_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


def resolve_dated_filename(base_filename: str, params: dict[str, Any] | None) -> str:
    """Replace ``{param}`` placeholders in an artifact basename from task params.

    ``ticker`` values are sanitized (``.`` → ``_``).
    Missing params leave the placeholder unchanged (e.g. unconfirmed ticker).
    """
    name = str(base_filename or "").strip()
    if not name:
        return name
    params = params or {}

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        raw = str(params.get(key) or "").strip()
        if not raw:
            return match.group(0)
        if key == "ticker":
            return raw.replace(".", "_")
        return raw

    return _PLACEHOLDER_RE.sub(_replace, name)


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
