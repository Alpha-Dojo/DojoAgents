"""Canonical session/run envelope around one AgentLoop invocation."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, replace
from typing import Any

from dojoagents.agent.events import AgentEvent, AgentEventSink
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
)
from dojoagents.sessions.run_coordinator import RunCoordinator
from dojoagents.sessions.service import SessionService


def _history_message(record: SessionMessageRecord) -> dict[str, Any]:
    message: dict[str, Any] = {"role": record.role, "content": record.content}
    if record.message_id:
        message["message_id"] = record.message_id
    return message


class _DurableEventWriter:
    """Persist AgentEventSink output in order while the run is still active."""

    def __init__(self, coordinator: RunCoordinator, sink: AgentEventSink) -> None:
        self.coordinator = coordinator
        self.sink = sink
        self.queue: asyncio.Queue[AgentEvent | None] = asyncio.Queue()
        self._closed = False
        self.sink.add_listener(self._enqueue)
        self.task = asyncio.create_task(
            self._run(),
            name=f"dojo-events:{coordinator.run_id}",
        )

    def _enqueue(self, event: AgentEvent) -> None:
        if not self._closed:
            self.queue.put_nowait(event)

    async def _persist(self, events: list[AgentEvent]) -> None:
        if not events:
            return
        await self.coordinator.append_events(tuple((event.type, event.to_dict()) for event in events))
        # RunCoordinator's size threshold reduces store calls for bursts, while
        # this explicit flush guarantees that an idle SSE reader sees the burst
        # before the Agent turn finishes.
        await self.coordinator.flush()
        LOGGER.debug(
            "Canonical run events persisted: run_id=%s count=%d first_seq=%d last_seq=%d",
            self.coordinator.run_id,
            len(events),
            events[0].seq,
            events[-1].seq,
        )

    async def _run(self) -> None:
        while True:
            item = await self.queue.get()
            if item is None:
                return
            pending = [item]
            await asyncio.sleep(0)
            while len(pending) < self.coordinator.service.config.runtime.event_batch_size:
                try:
                    queued = self.queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                if queued is None:
                    await self._persist(pending)
                    return
                pending.append(queued)
            await self._persist(pending)

    async def close(self) -> None:
        if self._closed:
            await self.task
            return
        self._closed = True
        self.sink.remove_listener(self._enqueue)
        self.queue.put_nowait(None)
        await self.task


class _RunHeartbeat:
    """Renew the session lease and convert durable cancellation into task cancellation."""

    def __init__(self, coordinator: RunCoordinator, owner_task: asyncio.Task[Any]) -> None:
        self.coordinator = coordinator
        self.owner_task = owner_task
        configured = float(coordinator.service.config.runtime.heartbeat_seconds)
        self.interval = max(0.1, configured)
        self.task = asyncio.create_task(
            self._run(),
            name=f"dojo-heartbeat:{coordinator.run_id}",
        )

    async def _run(self) -> None:
        try:
            while True:
                await asyncio.sleep(self.interval)
                result = await self.coordinator.heartbeat()
                if result.cancellation_requested:
                    LOGGER.info(
                        "Canonical run observed cancellation request: run_id=%s session_id=%s",
                        self.coordinator.run_id,
                        self.coordinator.session_id,
                    )
                    self.owner_task.cancel()
                    return
        except asyncio.CancelledError:
            raise
        except Exception:
            LOGGER.exception(
                "Canonical run heartbeat failed: run_id=%s session_id=%s",
                self.coordinator.run_id,
                self.coordinator.session_id,
            )
            self.owner_task.cancel()

    async def close(self) -> None:
        if not self.task.done():
            self.task.cancel()
        try:
            await self.task
        except asyncio.CancelledError:
            pass


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
    event_writer: _DurableEventWriter
    heartbeat: _RunHeartbeat
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
        LOGGER.info(
            "Canonical agent run started: run_id=%s session_id=%s harness_id=%s lease_expires_at=%s",
            run_id,
            request.session_id,
            descriptor.id,
            coordinator.handle.lease.expires_at.isoformat() if coordinator.handle is not None else None,
        )
        sink = event_sink or AgentEventSink(run_id=run_id, session_id=request.session_id)
        owner_task = asyncio.current_task()
        if owner_task is None:
            raise RuntimeError("canonical run requires an active asyncio task")
        event_writer = _DurableEventWriter(coordinator, sink)
        heartbeat = _RunHeartbeat(coordinator, owner_task)
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
            event_writer=event_writer,
            heartbeat=heartbeat,
            agent_id=agent_id,
            memory_sync_worker=memory_sync_worker,
        )

    async def _prepare_terminal(self) -> None:
        await self.heartbeat.close()
        await self.event_writer.close()

    async def commit(self, response: AgentResponse) -> TurnRecord:
        principal = self.request.principal
        assert principal is not None
        LOGGER.info(
            "Canonical agent run commit started: run_id=%s session_id=%s buffered_event_count=%d",
            self.coordinator.run_id,
            self.request.session_id,
            len(self.event_sink.events),
        )
        await self._prepare_terminal()
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
        # Invocation-level usage is appended immediately by UsageCollector.
        # Persisting the Turn aggregate here would double-count the same calls.
        committed = await self.coordinator.commit(turn, messages=messages)
        LOGGER.info(
            "Canonical agent run committed: run_id=%s session_id=%s persisted_event_count=%d",
            self.coordinator.run_id,
            self.request.session_id,
            len(self.event_sink.events),
        )
        if self.memory_sync_worker is not None:
            try:
                await self.memory_sync_worker.sync_pending(principal, self.request.session_id)
            except Exception:
                LOGGER.exception("Post-commit session memory sync failed")
        return committed

    async def fail(self, error: BaseException) -> None:
        LOGGER.exception(
            "Canonical agent run failing: run_id=%s session_id=%s buffered_event_count=%d error_type=%s error=%s",
            self.coordinator.run_id,
            self.request.session_id,
            len(self.event_sink.events),
            type(error).__name__,
            error,
        )
        if not self.event_sink.events or self.event_sink.events[-1].get("type") not in {"done", "error"}:
            self.event_sink.error(str(error), code="agent_run_failed")
        await self._prepare_terminal()
        await self.coordinator.fail({"code": "agent_run_failed", "type": type(error).__name__, "message": str(error)})

    async def cancel(self) -> None:
        if not self.event_sink.events or self.event_sink.events[-1].get("type") not in {"done", "error"}:
            self.event_sink.error("Run cancelled", code="cancelled")
        await self._prepare_terminal()
        await self.coordinator.cancel({"code": "agent_run_cancelled"})
