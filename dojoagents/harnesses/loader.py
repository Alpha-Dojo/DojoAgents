"""Deterministic Python harness loading without import-path mutation."""

from __future__ import annotations

import importlib
import inspect
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from dojoagents.config.models import HarnessConfig

from .base import AgentHarness, validate_harness
from .errors import HarnessLoadError, InvalidHarnessError

_BUILT_IN_ALIASES = {
    "financial": "dojoagents.harnesses.built_in.financial:create_harness",
}


@dataclass(frozen=True)
class LoadedHarness:
    harness: AgentHarness
    resolved_factory: str


class HarnessLoader:
    def __init__(self, aliases: Mapping[str, str] | None = None) -> None:
        self._aliases = {**_BUILT_IN_ALIASES, **dict(aliases or {})}

    @staticmethod
    def _resolve(target: str) -> Any:
        if ":" not in target:
            raise HarnessLoadError("harness factory must use an explicit module:attribute path")
        module_name, attribute = target.split(":", 1)
        if not module_name.strip() or not attribute.strip():
            raise HarnessLoadError("harness factory must use an explicit module:attribute path")
        try:
            module = importlib.import_module(module_name)
            return getattr(module, attribute)
        except Exception as exc:
            raise HarnessLoadError(f"failed to load harness factory '{target}': {type(exc).__name__}") from exc

    @staticmethod
    def _instantiate(factory: Any, config: Mapping[str, Any], context: Any) -> Any:
        try:
            signature = inspect.signature(factory)
            positional = [
                parameter
                for parameter in signature.parameters.values()
                if parameter.kind in (parameter.POSITIONAL_ONLY, parameter.POSITIONAL_OR_KEYWORD) and parameter.default is parameter.empty
            ]
            if not positional:
                return factory()
            if len(positional) == 1:
                return factory(dict(config))
            return factory(dict(config), context)
        except (HarnessLoadError, InvalidHarnessError):
            raise
        except Exception as exc:
            raise HarnessLoadError(f"harness factory invocation failed: {type(exc).__name__}") from exc

    def load(self, config: HarnessConfig, *, context: Any = None) -> LoadedHarness:
        if config.factory and config.manifest:
            raise HarnessLoadError("harness factory and manifest are mutually exclusive")
        if config.manifest:
            from .declarative import DeclarativeHarness
            from .schema import load_manifest

            path = config.manifest
            if context is not None and not str(path).startswith("/"):
                path = context.config_dir / str(path)
            harness = validate_harness(DeclarativeHarness(load_manifest(path), context))
            if harness.descriptor.id != config.id:
                raise InvalidHarnessError(f"expected harness descriptor ID '{config.id}', manifest produced '{harness.descriptor.id}'")
            return LoadedHarness(harness=harness, resolved_factory=f"manifest:{Path(path).resolve()}")
        target = config.factory or self._aliases.get(config.id)
        if not target:
            raise HarnessLoadError(f"no harness factory configured for '{config.id}'")
        candidate = self._instantiate(self._resolve(target), config.config, context)
        harness = validate_harness(candidate)
        if harness.descriptor.id != config.id:
            raise InvalidHarnessError(f"expected harness descriptor ID '{config.id}', factory produced '{harness.descriptor.id}'")
        return LoadedHarness(harness=harness, resolved_factory=target)


__all__ = ["HarnessLoadError", "HarnessLoader", "LoadedHarness"]
