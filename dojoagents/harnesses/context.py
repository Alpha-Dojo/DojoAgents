"""Capability-limited contexts passed to harness extension points."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from dojoagents.config.models import AgentsConfig
from dojoagents.sessions.models import SessionPrincipal

from .state import HarnessSessionState, HarnessTurnState


def _immutable_copy(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(value))


@dataclass(frozen=True)
class HarnessBuildContext:
    """Inputs available while a harness declares its capabilities."""

    config: AgentsConfig
    harness_config: Mapping[str, Any]
    config_dir: Path
    workdir: Path
    host: Any
    logger: Any

    def __post_init__(self) -> None:
        object.__setattr__(self, "harness_config", _immutable_copy(self.harness_config))


@dataclass(frozen=True)
class HarnessRuntimeContext:
    """Runtime facilities exposed after capability composition."""

    capabilities: Any
    services: Mapping[str, Any]
    logger: Any
    session_state_facade: Any | None = None
    object_facade: Any | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "services", _immutable_copy(self.services))


@dataclass(frozen=True)
class HarnessSessionContext:
    """Identity and state visible while handling one session."""

    principal: SessionPrincipal
    session_id: str
    state: HarnessSessionState

    def __post_init__(self) -> None:
        if type(self.state) is not HarnessSessionState:
            raise TypeError("state must be HarnessSessionState")
        if not self.session_id.strip():
            raise ValueError("session_id must not be blank")


class HarnessSessionStateFacade:
    """Creates only current-Harness state handles from an authenticated session context."""

    def __init__(self, service: Any, descriptor: Any, codec: Any | None) -> None:
        self._service = service
        self._descriptor = descriptor
        self._codec = codec

    @property
    def service(self) -> Any:
        return self._service

    def for_session(self, session: HarnessSessionContext) -> Any:
        if not isinstance(session, HarnessSessionContext):
            raise TypeError("session must be HarnessSessionContext")
        return self._service.harness_session(
            session.principal,
            session.session_id,
            self._descriptor.id,
            self._descriptor.version,
            self._descriptor.state_schema_version,
            codec=self._codec,
        )


class HarnessObjectFacade:
    """Creates an object writer scoped to an authenticated session context."""

    def __init__(self, service: Any) -> None:
        self._service = service

    def for_session(self, session: HarnessSessionContext) -> Any:
        if not isinstance(session, HarnessSessionContext):
            raise TypeError("session must be HarnessSessionContext")
        return self._service.object_writer(session.principal, session.session_id)


@dataclass
class HarnessTurnContext:
    """Per-turn execution context and trace accumulation."""

    request: Any
    session: HarnessSessionContext
    turn_state: HarnessTurnState = field(default_factory=HarnessTurnState)
    tool_calls: list[Any] = field(default_factory=list)
    tool_results: list[Any] = field(default_factory=list)
    blocked_calls: list[Any] = field(default_factory=list)
    trace: list[Any] = field(default_factory=list)
    final_response: Any | None = None

    def __post_init__(self) -> None:
        if type(self.turn_state) is not HarnessTurnState:
            raise TypeError("turn_state must be HarnessTurnState")


# Concise public spelling retained for turn-hook ergonomics.
TurnContext = HarnessTurnContext
