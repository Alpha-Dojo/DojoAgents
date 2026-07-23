"""Strict v1alpha1 declarative Harness manifest validation."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from dojoagents.config.loader import load_yaml_mapping
from dojoagents.harnesses.errors import HarnessLoadError

_FACTORY = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*:[A-Za-z_][A-Za-z0-9_]*$")
_TOP = {"apiVersion", "kind", "metadata", "implementation", "components", "config"}
_METADATA = {"id", "version", "display_name", "description", "state_schema_version", "supported_channels"}
_COMPONENTS = {"identity", "prompts", "skills", "tools", "mcp", "memory", "policies", "tasks", "pipelines", "services", "surfaces", "state"}
_COMMON = {
    "id",
    "factory",
    "priority",
    "dependencies",
    "required_services",
    "required_tools",
    "channels",
    "config",
    "path",
    "value",
    "phase",
    "tool_names",
    "exclusive",
    "match_kinds",
    "required",
}


def _reject_unknown(value: dict[str, Any], allowed: set[str], location: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise HarnessLoadError(f"{location} contains unknown fields: {', '.join(unknown)}")


def _safe_path(root: Path, raw: str, location: str) -> Path:
    path = (root / raw).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise HarnessLoadError(f"{location} escapes manifest directory") from exc
    return path


def load_manifest(path: str | Path) -> dict[str, Any]:
    manifest_path = Path(path).expanduser().resolve()
    raw = load_yaml_mapping(manifest_path)
    _reject_unknown(raw, _TOP, "manifest")
    if raw.get("apiVersion") != "dojoagents/v1alpha1" or raw.get("kind") != "Harness":
        raise HarnessLoadError("manifest must be dojoagents/v1alpha1 kind Harness")
    metadata = raw.get("metadata")
    if not isinstance(metadata, dict):
        raise HarnessLoadError("manifest metadata must be a mapping")
    _reject_unknown(metadata, _METADATA, "metadata")
    for key in ("id", "version", "display_name"):
        if not str(metadata.get(key) or "").strip():
            raise HarnessLoadError(f"metadata.{key} is required")
    implementation = raw.get("implementation") or {}
    if not isinstance(implementation, dict):
        raise HarnessLoadError("implementation must be a mapping")
    _reject_unknown(implementation, {"factory"}, "implementation")
    if implementation:
        factory = str(implementation.get("factory") or "")
        if not _FACTORY.fullmatch(factory):
            raise HarnessLoadError("implementation.factory must use module:attribute")
    components = raw.get("components") or {}
    if not isinstance(components, dict):
        raise HarnessLoadError("components must be a mapping")
    _reject_unknown(components, _COMPONENTS, "components")
    seen: set[str] = set()
    for kind, entries in components.items():
        if kind == "identity":
            entries = [entries]
        if not isinstance(entries, list):
            raise HarnessLoadError(f"components.{kind} must be a list")
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise HarnessLoadError(f"components.{kind}[{index}] must be a mapping")
            _reject_unknown(entry, _COMMON, f"components.{kind}[{index}]")
            component_id = str(entry.get("id") or "").strip()
            if not component_id:
                raise HarnessLoadError(f"components.{kind}[{index}].id is required")
            if component_id in seen:
                raise HarnessLoadError(f"duplicate component id: {component_id}")
            seen.add(component_id)
            if entry.get("factory") and not _FACTORY.fullmatch(str(entry["factory"])):
                raise HarnessLoadError(f"components.{kind}[{index}].factory is invalid")
            if entry.get("path"):
                _safe_path(manifest_path.parent, str(entry["path"]), f"components.{kind}[{index}].path")
            for forbidden in ("sql", "shell", "command"):
                if forbidden in entry:
                    raise HarnessLoadError(f"declarative Harness does not allow {forbidden}")
    return {**raw, "_manifest_path": str(manifest_path)}


__all__ = ["load_manifest"]
