"""State containers owned by each harness lifecycle scope."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, runtime_checkable


@dataclass
class HarnessRuntimeState:
    """Mutable state shared only by one instantiated harness runtime."""

    values: dict[str, Any] = field(default_factory=dict)


@dataclass
class HarnessSessionState:
    """Mutable state scoped to one canonical session."""

    values: dict[str, Any] = field(default_factory=dict)


@dataclass
class HarnessTurnState:
    """Ephemeral mutable state scoped to one agent turn."""

    values: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class HarnessStateCodec(Protocol):
    """Converts harness session state to backend-neutral persisted data."""

    def encode(self, state: HarnessSessionState) -> Mapping[str, Any]: ...

    def decode(self, data: Mapping[str, Any]) -> HarnessSessionState: ...

    def migrate(
        self,
        state: Mapping[str, Any],
        *,
        from_version: str,
        from_schema_version: int,
        to_version: str,
        to_schema_version: int,
    ) -> Mapping[str, Any]: ...
