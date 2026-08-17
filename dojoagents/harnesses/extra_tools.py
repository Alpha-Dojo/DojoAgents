"""Safe loader for configured supplemental ToolSpec providers."""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path
from typing import Iterable

from dojoagents.config.loader import load_yaml_mapping
from dojoagents.tools.registry import ToolSpec

from .errors import CapabilityConflictError


def _roots(value: str | Path | Iterable[str | Path]) -> tuple[Path, ...]:
    if isinstance(value, (str, Path)):
        value = (value,)
    return tuple(Path(root).expanduser().resolve() for root in value)


def _safe_module_path(root: Path, configured: str) -> Path:
    candidate = (root / configured).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError(f"extra tool module path escape rejected: {configured}")
    if not candidate.is_file() or candidate.suffix != ".py":
        raise ValueError(f"extra tool module must be an existing Python file: {configured}")
    return candidate


def _load_root(root: Path) -> tuple[ToolSpec, ...]:
    manifest_path = root / "tools.yaml"
    manifest = load_yaml_mapping(manifest_path)
    unknown = set(manifest).difference({"module", "factory"})
    if unknown:
        raise ValueError(f"unknown tools.yaml fields: {', '.join(sorted(unknown))}")
    module_value = manifest.get("module")
    factory_name = manifest.get("factory")
    if not isinstance(module_value, str) or not isinstance(factory_name, str):
        raise ValueError("tools.yaml requires string module and factory fields")
    module_path = _safe_module_path(root, module_value)
    digest = hashlib.sha256(str(root).encode() + b"\0" + module_path.read_bytes()).hexdigest()[:20]
    module_name = f"dojoagents_extra_tools_{digest}"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot create module spec for {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        factory = getattr(module, factory_name)
        result = tuple(factory())
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    if any(not isinstance(item, ToolSpec) for item in result):
        sys.modules.pop(module_name, None)
        raise TypeError(f"extra tool factory '{factory_name}' must return only ToolSpec values")
    return result


def load_extra_tools(
    roots: str | Path | Iterable[str | Path],
    *,
    reserved_tools: dict[str, str] | None = None,
) -> tuple[ToolSpec, ...]:
    """Load isolated providers and reject every tool-name override."""

    seen = dict(reserved_tools or {})
    loaded: list[ToolSpec] = []
    for root in _roots(roots):
        source = f"extra-tools:{root / 'tools.yaml'}"
        for tool in _load_root(root):
            existing = seen.get(tool.name)
            if existing is not None:
                raise CapabilityConflictError(f"duplicate tool '{tool.name}' from {existing} conflicts with {source}")
            seen[tool.name] = source
            loaded.append(tool)
    return tuple(loaded)
