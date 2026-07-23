from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from dojoagents.sessions.errors import SessionConflictError
from dojoagents.sessions.models import (
    BeginRunCommand,
    CommitTurnCommand,
    FinishRunCommand,
    HeartbeatResult,
    JsonValue,
    RunHandle,
    SessionEvent,
    SessionMessageRecord,
    SessionPrincipal,
    TurnRecord,
    UsageRecord,
    utc_now,
)
from dojoagents.sessions.service import SessionService


@dataclass(frozen=True)
class PendingEvent:
    event_type: str
    payload: JsonValue


class RunCoordinator:
    def __init__(
        self,
        service: SessionService,
        principal: SessionPrincipal,
        session_id: str,
        *,
        holder_id: str,
        model: str,
    ) -> None:
        service.require_persistence("run coordination")
        self.service = service
        self.principal = principal
        self.session_id = session_id
        self.holder_id = holder_id
        self.model = model
        self.handle: RunHandle | None = None
        self._buffer: list[SessionEvent] = []
        self._next_sequence = 1
        self._terminal: Any = None

    def _active_handle(self) -> RunHandle:
        if self.handle is None:
            raise SessionConflictError("run has not started")
        return self.handle

    @property
    def run_id(self) -> str:
        return self._active_handle().run.run_id

    async def begin(self, run_id: str, *, idempotency_key: str) -> RunHandle:
        command = BeginRunCommand(
            session_id=self.session_id,
            run_id=run_id,
            model=self.model,
            idempotency_key=idempotency_key,
            holder_id=self.holder_id,
            lease_seconds=self.service.config.runtime.lease_seconds,
        )
        self.handle = await self.service.begin_run_with_lease(self.principal, command)
        existing = await self.service.read_events(self.principal, run_id, after_seq=0, limit=100_000)
        self._next_sequence = (existing.items[-1].sequence + 1) if existing.items else 1
        return self.handle

    async def append_events(self, events: Sequence[tuple[str, JsonValue]]) -> tuple[SessionEvent, ...]:
        handle = self._active_handle()
        if self._terminal is not None:
            raise SessionConflictError("run is already terminal")
        created: list[SessionEvent] = []
        for event_type, payload in events:
            sequence = self._next_sequence
            self._next_sequence += 1
            event = SessionEvent(
                run_id=handle.run.run_id,
                sequence=sequence,
                event_type=event_type,
                payload=payload,
                lease_id=handle.lease.lease_id,
                fencing_token=handle.lease.fencing_token,
                idempotency_key=f"{handle.run.run_id}:event:{sequence}",
            )
            self._buffer.append(event)
            created.append(event)
        if len(self._buffer) >= self.service.config.runtime.event_batch_size:
            await self.flush()
        return tuple(created)

    async def flush(self) -> None:
        if not self._buffer:
            return
        handle = self._active_handle()
        pending = tuple(self._buffer)
        await self.service.append_events(self.principal, handle.run.run_id, pending)
        del self._buffer[: len(pending)]

    async def heartbeat(self) -> HeartbeatResult:
        handle = self._active_handle()
        remaining = (handle.lease.expires_at - utc_now()).total_seconds()
        if remaining <= self.service.config.runtime.lease_seconds / 3:
            renewed = await self.service.renew_lease(self.principal, handle.lease)
            self.handle = RunHandle(run=handle.run, lease=renewed)
            handle = self.handle
        run = await self.service.get_run(self.principal, handle.run.run_id)
        self.handle = RunHandle(run=run, lease=handle.lease)
        return HeartbeatResult(lease=handle.lease, cancellation_requested=run.cancellation_requested)

    async def commit(
        self,
        turn: TurnRecord,
        *,
        messages: tuple[SessionMessageRecord, ...] = (),
        usage: tuple[UsageRecord, ...] = (),
    ) -> TurnRecord:
        if self._terminal is not None:
            if isinstance(self._terminal, TurnRecord):
                return self._terminal
            raise SessionConflictError("run already ended without a committed turn")
        await self.flush()
        handle = self._active_handle()
        result = await self.service.commit_turn(
            self.principal,
            CommitTurnCommand(handle.run.run_id, handle.lease, turn, messages, usage),
        )
        self._terminal = result
        return result

    async def fail(self, error: dict[str, JsonValue] | None = None):
        if self._terminal is not None:
            return self._terminal
        await self.flush()
        handle = self._active_handle()
        result = await self.service.fail_run(
            self.principal,
            FinishRunCommand(handle.run.run_id, handle.lease, error),
        )
        self._terminal = result
        return result

    async def cancel(self, error: dict[str, JsonValue] | None = None):
        if self._terminal is not None:
            return self._terminal
        await self.flush()
        handle = self._active_handle()
        result = await self.service.cancel_run(
            self.principal,
            FinishRunCommand(handle.run.run_id, handle.lease, error),
        )
        self._terminal = result
        return result

    async def request_cancel(self, run_id: str | None = None):
        target = run_id or self._active_handle().run.run_id
        return await self.service.request_cancel(self.principal, target)

    async def read_events(self, *, after_seq: int = 0, limit: int = 100):
        handle = self._active_handle()
        return await self.service.read_events(self.principal, handle.run.run_id, after_seq=after_seq, limit=limit)
