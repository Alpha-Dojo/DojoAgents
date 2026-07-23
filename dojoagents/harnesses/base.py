"""Public harness capability contract."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from .context import HarnessBuildContext, HarnessRuntimeContext
from .errors import InvalidHarnessError


@dataclass(frozen=True)
class HarnessDescriptor:
    """Stable metadata used to select and persist a harness."""

    id: str
    version: str
    display_name: str
    description: str = ""
    state_schema_version: int = 1
    supported_channels: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("id", "version", "display_name"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} must not be blank")
        if self.state_schema_version < 1:
            raise ValueError("state_schema_version must be at least 1")
        object.__setattr__(self, "supported_channels", tuple(self.supported_channels))


@runtime_checkable
class AgentHarness(Protocol):
    """One scenario-specific capability plugin bound to an agent instance."""

    descriptor: HarnessDescriptor

    def configure(self, builder: Any, context: HarnessBuildContext) -> None: ...

    async def startup(self, context: HarnessRuntimeContext) -> None: ...

    async def shutdown(self, context: HarnessRuntimeContext) -> None: ...


def validate_harness(candidate: Any) -> AgentHarness:
    """Validate lifecycle method shapes before runtime composition begins."""

    if not isinstance(getattr(candidate, "descriptor", None), HarnessDescriptor):
        raise InvalidHarnessError("harness descriptor must be a HarnessDescriptor")

    configure = getattr(candidate, "configure", None)
    startup = getattr(candidate, "startup", None)
    shutdown = getattr(candidate, "shutdown", None)
    if not callable(configure) or inspect.iscoroutinefunction(configure):
        raise InvalidHarnessError("harness configure must be synchronous")
    if not inspect.iscoroutinefunction(startup):
        raise InvalidHarnessError("harness startup must be asynchronous")
    if not inspect.iscoroutinefunction(shutdown):
        raise InvalidHarnessError("harness shutdown must be asynchronous")
    return candidate
