"""Dependency-ordered, all-or-nothing harness service lifecycle."""

from __future__ import annotations

import inspect
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from .capabilities import ServiceSpec
from .errors import HarnessLifecycleError


async def _resolve(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


class LifecycleManager:
    def __init__(self, specs: Iterable[ServiceSpec]) -> None:
        self._specs = tuple(specs)
        self._started: list[tuple[ServiceSpec, Any]] = []
        self._services: dict[str, Any] = {}
        self._shutdown = False

    def _topological_order(self) -> tuple[ServiceSpec, ...]:
        by_id = {spec.component_id: spec for spec in self._specs}
        if len(by_id) != len(self._specs):
            raise HarnessLifecycleError("duplicate service IDs in lifecycle graph")
        for spec in self._specs:
            missing = set(spec.dependencies).difference(by_id)
            if missing:
                raise HarnessLifecycleError(f"service '{spec.component_id}' has missing dependencies: {', '.join(sorted(missing))}")
        pending = dict(by_id)
        resolved: set[str] = set()
        ordered: list[ServiceSpec] = []
        while pending:
            ready = sorted(
                (spec for spec in pending.values() if set(spec.dependencies) <= resolved),
                key=lambda item: item.component_id,
            )
            if not ready:
                raise HarnessLifecycleError(f"service dependency cycle: {', '.join(sorted(pending))}")
            for spec in ready:
                ordered.append(spec)
                resolved.add(spec.component_id)
                pending.pop(spec.component_id)
        return tuple(ordered)

    async def startup(self) -> Mapping[str, Any]:
        if self._started:
            return MappingProxyType(dict(self._services))
        self._shutdown = False
        try:
            for spec in self._topological_order():
                if spec.factory is None:
                    raise HarnessLifecycleError(f"service '{spec.component_id}' has no factory")
                service = await _resolve(spec.factory())
                # Register before startup so a callback that partially acquires
                # resources and then raises is still included in rollback.
                self._started.append((spec, service))
                self._services[spec.component_id] = service
                callback = spec.startup or getattr(service, "startup", None)
                if callback is not None:
                    if spec.startup is not None:
                        await _resolve(callback(service))
                    else:
                        await _resolve(callback())
                health = spec.health_check or getattr(service, "health", None)
                if health is not None:
                    result = await _resolve(health(service) if spec.health_check is not None else health())
                    healthy = result if isinstance(result, bool) else getattr(result, "healthy", False)
                    if not healthy:
                        raise HarnessLifecycleError(f"service '{spec.component_id}' failed health check")
        except Exception as exc:
            failed_id = spec.component_id if "spec" in locals() else "graph"
            await self._rollback()
            if isinstance(exc, HarnessLifecycleError):
                raise
            raise HarnessLifecycleError(f"service '{failed_id}' startup failed: {exc}") from exc
        return MappingProxyType(dict(self._services))

    async def _rollback(self) -> None:
        for spec, service in reversed(self._started):
            callback = spec.shutdown or getattr(service, "shutdown", None)
            if callback is None:
                continue
            try:
                if spec.shutdown is not None:
                    await _resolve(callback(service))
                else:
                    await _resolve(callback())
            except Exception:
                # Preserve the original startup failure; normal shutdown reports failures.
                pass
        self._started.clear()
        self._services.clear()

    async def shutdown(self) -> None:
        if self._shutdown:
            return
        errors: list[str] = []
        for spec, service in reversed(self._started):
            callback = spec.shutdown or getattr(service, "shutdown", None)
            if callback is None:
                continue
            try:
                if spec.shutdown is not None:
                    await _resolve(callback(service))
                else:
                    await _resolve(callback())
            except Exception as exc:
                errors.append(f"{spec.component_id}: {exc}")
        self._started.clear()
        self._services.clear()
        self._shutdown = True
        if errors:
            raise HarnessLifecycleError("service shutdown failed: " + "; ".join(errors))
