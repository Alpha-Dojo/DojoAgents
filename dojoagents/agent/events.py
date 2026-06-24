from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AgentEvent:
    type: str
    run_id: str
    seq: int
    session_id: str
    schema_version: str = "2.0"
    timestamp: str = field(default_factory=_utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ContentDeltaEvent(AgentEvent):
    text: str = ""


@dataclass
class PhaseChangedEvent(AgentEvent):
    phase: str = "planning"


@dataclass
class ThinkingStartedEvent(AgentEvent):
    summary: str = ""


@dataclass
class ThinkingDeltaEvent(AgentEvent):
    text: str = ""


@dataclass
class ThinkingEndedEvent(AgentEvent):
    summary: str = ""


@dataclass
class RetryScheduledEvent(AgentEvent):
    attempt: int = 1
    max_attempts: int = 1
    text: str = ""


@dataclass
class ToolStartedEvent(AgentEvent):
    call_id: str = ""
    tool: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolFinishedEvent(AgentEvent):
    call_id: str = ""
    tool: str = ""
    ok: bool = True
    content: str = ""
    error: str = ""
    latency_ms: int = 0
    truncated: bool = False
    data: Any = None
    viz_blocks: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    resource_changes: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class EvaluationHintEvent(AgentEvent):
    text: str = ""
    issues: list[str] = field(default_factory=list)


@dataclass
class RunCompletedEvent(AgentEvent):
    model_id: str = ""
    tool_trace: list[dict[str, Any]] = field(default_factory=list)
    tool_steps: int = 0


@dataclass
class RunFailedEvent(AgentEvent):
    message: str = ""
    code: str = "runtime_error"


class AgentEventSink:
    def __init__(
        self,
        *,
        run_id: str,
        session_id: str,
        emit: Callable[[AgentEvent], None] | None = None,
    ) -> None:
        self.run_id = run_id
        self.session_id = session_id
        self._emit = emit
        self._seq = 0
        self.events: list[dict[str, Any]] = []

    def _dispatch(self, event_cls: type[AgentEvent], **payload: Any) -> dict[str, Any]:
        self._seq += 1
        event = event_cls(
            run_id=self.run_id,
            seq=self._seq,
            session_id=self.session_id,
            **payload,
        )
        event_payload = event.to_dict()
        self.events.append(event_payload)
        if self._emit is not None:
            self._emit(event)
        return event_payload

    def delta(self, text: str) -> dict[str, Any]:
        return self._dispatch(ContentDeltaEvent, type="delta", text=text)

    def phase(self, phase: str) -> dict[str, Any]:
        return self._dispatch(PhaseChangedEvent, type="phase", phase=phase)

    def thinking_start(self, summary: str = "") -> dict[str, Any]:
        return self._dispatch(ThinkingStartedEvent, type="think_start", summary=summary)

    def thinking_delta(self, text: str) -> dict[str, Any]:
        return self._dispatch(ThinkingDeltaEvent, type="think_delta", text=text)

    def thinking_end(self, summary: str = "") -> dict[str, Any]:
        return self._dispatch(ThinkingEndedEvent, type="think_end", summary=summary)

    def retry(self, *, attempt: int, max_attempts: int, text: str = "") -> dict[str, Any]:
        return self._dispatch(
            RetryScheduledEvent,
            type="retry",
            attempt=attempt,
            max_attempts=max_attempts,
            text=text,
        )

    def tool_start(self, *, call_id: str, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self._dispatch(
            ToolStartedEvent,
            type="tool_start",
            call_id=call_id,
            tool=tool,
            arguments=arguments,
        )

    def tool_result(
        self,
        *,
        call_id: str,
        tool: str,
        ok: bool,
        content: str = "",
        error: str = "",
        latency_ms: int = 0,
        truncated: bool = False,
        data: Any = None,
        viz_blocks: list[dict[str, Any]] | None = None,
        artifacts: list[dict[str, Any]] | None = None,
        resource_changes: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return self._dispatch(
            ToolFinishedEvent,
            type="tool_result",
            call_id=call_id,
            tool=tool,
            ok=ok,
            content=content,
            error=error,
            latency_ms=latency_ms,
            truncated=truncated,
            data=data,
            viz_blocks=list(viz_blocks or []),
            artifacts=list(artifacts or []),
            resource_changes=list(resource_changes or []),
        )

    def eval_hint(self, text: str, issues: list[str] | None = None) -> dict[str, Any]:
        return self._dispatch(
            EvaluationHintEvent,
            type="eval_hint",
            text=text,
            issues=list(issues or []),
        )

    def done(
        self,
        *,
        model_id: str,
        tool_trace: list[dict[str, Any]] | None = None,
        tool_steps: int = 0,
    ) -> dict[str, Any]:
        return self._dispatch(
            RunCompletedEvent,
            type="done",
            model_id=model_id,
            tool_trace=list(tool_trace or []),
            tool_steps=tool_steps,
        )

    def error(self, message: str, code: str = "runtime_error") -> dict[str, Any]:
        return self._dispatch(RunFailedEvent, type="error", message=message, code=code)
