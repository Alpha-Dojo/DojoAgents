"""Framework-neutral telemetry hooks.

DojoAgents is a public framework and must not carry project-specific storage
semantics. This module lets a host application (e.g. dojoagent-service) observe
LLM calls, tool calls and run boundaries via *neutral* events, then decide for
itself how to persist them (usage tables, run-timing rows, a trace backend).

Design constraints (mirrors OpenTelemetry GenAI semantic-convention guidance):

* Events are plain frozen dataclasses — no storage schema, no field names that
  leak the host's column names.
* ``emit`` is synchronous and never awaits: observability must not perturb the
  run path. Every hook is wrapped in try/except so a broken sink only logs a
  warning, never fails the request.
* Hooks are registered process-wide via :func:`register`; the registry is a
  module-level list so registration is one line at app startup.

Timing values are monotonic-clock based (``time.perf_counter``) where the caller
has them; wall-clock fallbacks are documented per field.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

LOGGER = logging.getLogger("dojoagents.telemetry")

# Correlation id for events emitted deep inside the framework (e.g. the tool
# executor, which has no run parameter). The host run loop binds it once per
# run; asyncio tasks spawned inside that run inherit it automatically. This is
# process-local context propagation — the observability equivalent of an OTel
# span context — not a data channel into persistence.
_ACTIVE_RUN_ID: ContextVar[str] = ContextVar("dojoagents_active_run_id", default="")


class bind_run_id:
    """Bind the emitting run id for the enclosing context (run loop scope)."""

    __slots__ = ("_token",)

    def __init__(self, run_id: str) -> None:
        self._token = _ACTIVE_RUN_ID.set(run_id or "")

    def unbind(self) -> None:
        _ACTIVE_RUN_ID.reset(self._token)

    def __enter__(self) -> "bind_run_id":
        return self

    def __exit__(self, *exc: object) -> None:
        self.unbind()


def current_run_id() -> str:
    return _ACTIVE_RUN_ID.get()


@dataclass(frozen=True)
class LLMCallEvent:
    """One completed LLM invocation, emitted once per model call."""

    run_id: str
    model: str
    provider: str
    started_at: float | None = None
    request_ms: int = 0
    # Time to first chunk (reasoning included) / first content chunk / decode
    # window. None means "not measurable on this provider or path".
    ttft_ms: int | None = None
    ttfc_ms: int | None = None
    decode_ms: int | None = None
    usage: Mapping[str, int] | None = None
    status: str = "succeeded"
    error_code: str | None = None


@dataclass(frozen=True)
class LLMRequestEvent:
    """HTTP attempt/retry/final outcome, independent of log-level filtering."""

    run_id: str
    provider: str
    model: str
    event: str
    attempt: int
    outcome: str = ""
    elapsed_ms: float = 0


@dataclass(frozen=True)
class ToolCallEvent:
    """One completed tool invocation."""

    run_id: str
    tool_name: str
    call_id: str
    latency_ms: int = 0
    ok: bool = True
    # Optional per-tool internal spans (HTTP / DB / postprocess). Neutral dicts,
    # shape owned by the host.
    spans: tuple[Mapping[str, Any], ...] = ()
    # Aggregate sub-step breakdown (wait/handler/postprocess/total) alongside
    # ``spans``. Neutral mapping; None when the framework did not measure it.
    timing: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class RunEvent:
    """Run lifecycle boundary."""

    run_id: str
    session_id: str
    status: str = "succeeded"
    latency_ms: int = 0


class TelemetryHook(Protocol):
    """Contract a host implements to receive framework events."""

    def on_llm_call_end(self, event: LLMCallEvent) -> None: ...

    def on_tool_call_end(self, event: ToolCallEvent) -> None: ...

    def on_run_end(self, event: RunEvent) -> None: ...


_HOOKS: list[TelemetryHook] = []


def register(hook: TelemetryHook) -> None:
    """Add a hook. Idempotent per instance; safe to call once at startup."""
    if hook not in _HOOKS:
        _HOOKS.append(hook)


def unregister(hook: TelemetryHook) -> None:
    try:
        _HOOKS.remove(hook)
    except ValueError:
        pass


def emit(event: object) -> None:
    """Fan an event out to every hook. Never raises."""
    if not _HOOKS:
        return
    for hook in _HOOKS:
        try:
            if isinstance(event, LLMRequestEvent):
                callback = getattr(hook, "on_llm_request", None)
                if callback is not None:
                    callback(event)
            elif isinstance(event, LLMCallEvent):
                hook.on_llm_call_end(event)
            elif isinstance(event, ToolCallEvent):
                hook.on_tool_call_end(event)
            elif isinstance(event, RunEvent):
                hook.on_run_end(event)
        except Exception:  # noqa: BLE001 - telemetry must never fail the run
            LOGGER.warning("telemetry hook %r failed for %s", hook, type(event).__name__, exc_info=True)


def _reset_for_tests() -> None:
    _HOOKS.clear()
