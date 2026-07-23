"""Canonical session/run envelope around one AgentLoop invocation."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from typing import Any

from dojoagents.agent.events import AgentEventSink
from dojoagents.agent.models import AgentResponse, ChatRequest
from dojoagents.harnesses.base import HarnessDescriptor
from dojoagents.logging import LOGGER
from dojoagents.sessions.errors import SessionNotFoundError
from dojoagents.sessions.memory_sync import SessionMemorySyncWorker
from dojoagents.sessions.models import (
    HistoryQuery,
    SessionCreateSpec,
    SessionMessageRecord,
    TurnQuery,
    TurnRecord,
    UsageRecord,
)
from dojoagents.sessions.run_coordinator import RunCoordinator
from dojoagents.sessions.service import SessionService


def _history_message(record: SessionMessageRecord) -> dict[str, Any]:
    message: dict[str, Any] = {"role": record.role, "content": record.content}
    if record.message_id:
        message["message_id"] = record.message_id
    return message


@dataclass
class CanonicalAgentRun:
    service: SessionService
    coordinator: RunCoordinator
    request: ChatRequest
    descriptor: HarnessDescriptor
    session_uid: str
    turn_id: str
    turn_sequence: int
    message_sequence: int
    event_sink: AgentEventSink
    agent_id: str
    memory_sync_worker: SessionMemorySyncWorker | None = None

    @classmethod
    async def begin(
        cls,
        service: SessionService,
        request: ChatRequest,
        descriptor: HarnessDescriptor,
        *,
        model: str,
        agent_id: str,
        event_sink: AgentEventSink | None = None,
        memory_sync_worker: SessionMemorySyncWorker | None = None,
    ) -> "CanonicalAgentRun":
        principal = request.principal
        if principal is None:  # ChatRequest validates this; defensive for alternate request implementations.
            raise ValueError("canonical sessions require a principal")
        try:
            session = await service.get_session(principal, request.session_id)
        except SessionNotFoundError:
            session = await service.create_session(
                principal,
                SessionCreateSpec(
                    session_id=request.session_id,
                    harness_id=descriptor.id,
                    harness_version=descriptor.version,
                    harness_state_schema_version=descriptor.state_schema_version,
                    title=request.message.strip().replace("\n", " ")[:80],
                    model=model,
                    metadata={"channel": request.channel},
                ),
            )
        if session.harness_id != descriptor.id:
            from dojoagents.sessions.errors import HarnessSessionIncompatibleError

            raise HarnessSessionIncompatibleError(f"session is bound to harness {session.harness_id!r}, not {descriptor.id!r}")

        history = await service.history(principal, request.session_id, HistoryQuery(limit=10_000))
        metadata = dict(request.metadata)
        metadata.setdefault("history", [_history_message(item) for item in history.items])
        request = replace(request, metadata=metadata)

        turns = await service.turns(principal, request.session_id, TurnQuery(limit=10_000))
        turn_sequence = max((item.sequence for item in turns.items), default=0) + 1
        message_sequence = max((item.sequence for item in history.items), default=0) + 1
        if event_sink is not None and event_sink.session_id != request.session_id:
            raise ValueError("event sink session_id does not match request session_id")
        run_id = str((event_sink.run_id if event_sink is not None else None) or metadata.get("run_id") or f"run-{uuid.uuid4().hex}")
        turn_id = str(metadata.get("turn_id") or f"turn-{uuid.uuid4().hex}")
        coordinator = RunCoordinator(
            service,
            principal,
            request.session_id,
            holder_id=f"agent:{agent_id}:{uuid.uuid4().hex}",
            model=model,
        )
        await coordinator.begin(run_id, idempotency_key=str(metadata.get("idempotency_key") or turn_id))
        sink = event_sink or AgentEventSink(run_id=run_id, session_id=request.session_id)
        return cls(
            service=service,
            coordinator=coordinator,
            request=request,
            descriptor=descriptor,
            session_uid=session.session_uid,
            turn_id=turn_id,
            turn_sequence=turn_sequence,
            message_sequence=message_sequence,
            event_sink=sink,
            agent_id=agent_id,
            memory_sync_worker=memory_sync_worker,
        )

    async def commit(self, response: AgentResponse) -> TurnRecord:
        principal = self.request.principal
        assert principal is not None
        if self.event_sink.events:
            await self.coordinator.append_events(tuple((str(event.get("type") or "agent_event"), dict(event)) for event in self.event_sink.events))
        usage_payload = response.metadata.get("usage") or {}
        usage: tuple[UsageRecord, ...] = ()
        if any(int(usage_payload.get(key) or 0) for key in ("prompt_tokens", "completion_tokens", "total_tokens")):
            usage = (
                UsageRecord(
                    usage_id=f"usage-{uuid.uuid4().hex}",
                    session_uid=self.session_uid,
                    run_id=self.coordinator.run_id,
                    provider="agent",
                    model=self.coordinator.model,
                    input_tokens=int(usage_payload.get("prompt_tokens") or 0),
                    output_tokens=int(usage_payload.get("completion_tokens") or 0),
                    idempotency_key=f"{self.turn_id}:usage",
                ),
            )
        messages = (
            SessionMessageRecord(
                self.session_uid,
                self.request.session_id,
                self.agent_id,
                self.message_sequence,
                "user",
                self.request.message,
                message_id=f"{self.turn_id}:user",
            ),
            SessionMessageRecord(
                self.session_uid,
                self.request.session_id,
                self.agent_id,
                self.message_sequence + 1,
                "assistant",
                response.content,
                message_id=f"{self.turn_id}:assistant",
            ),
        )
        turn = TurnRecord(
            session_uid=self.session_uid,
            session_id=self.request.session_id,
            run_id=self.coordinator.run_id,
            turn_id=self.turn_id,
            sequence=self.turn_sequence,
            input={"message": self.request.message, "context": self.request.context},
            output={"content": response.content},
            completion={"stopped": response.metadata.get("stopped")},
            tool_trace=tuple(response.metadata.get("tool_trace") or ()),
        )
        committed = await self.coordinator.commit(turn, messages=messages, usage=usage)
        if self.memory_sync_worker is not None:
            try:
                await self.memory_sync_worker.sync_pending(principal, self.request.session_id)
            except Exception:
                LOGGER.exception("Post-commit session memory sync failed")
        return committed

    async def fail(self, error: BaseException) -> None:
        await self.coordinator.fail({"code": "agent_run_failed", "type": type(error).__name__, "message": str(error)})

    async def cancel(self) -> None:
        await self.coordinator.cancel({"code": "agent_run_cancelled"})
