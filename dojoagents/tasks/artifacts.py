"""Task artifact filename helpers."""

from __future__ import annotations

import re
from typing import Any

from dojoagents.tasks.models import TaskArtifactSpec, TaskSpec

_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


def _sanitize_filename_token(key: str, value: str) -> str:
    """Make a param value safe to embed in a basename.

    - ``ticker``: ``.`` → ``_`` (e.g. ``0700.HK`` → ``0700_HK``)
    - ``sector_id`` / any token: ``/`` and ``\\`` → ``_`` (e.g. ``1/2/6`` → ``1_2_6``)
    """
    token = value
    if key == "ticker":
        token = token.replace(".", "_")
    return token.replace("/", "_").replace("\\", "_")


def resolve_filename_template(base_filename: str, params: dict[str, Any] | None) -> str:
    """Replace ``{param}`` placeholders in an artifact basename from task params.

    Missing params leave the placeholder unchanged (e.g. unconfirmed ticker / sector_id).
    Substituted tokens are sanitized for use as a single path segment.
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
        return _sanitize_filename_token(key, raw)

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
                "filename": resolve_filename_template(item.filename, params),
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
    return resolve_filename_template(artifact.filename, params)
