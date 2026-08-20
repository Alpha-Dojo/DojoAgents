from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from dojoagents.logging import LOGGER
from dojoagents.sessions.errors import SessionConflictError, SessionLeaseLostError
from dojoagents.sessions.models import (
    BeginRunCommand,
    CommitTurnCommand,
    ContextUsageSnapshot,
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
        self.terminal_event: SessionEvent | None = None

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

    async def append_usage(self, records: Sequence[UsageRecord]) -> tuple[UsageRecord, ...]:
        if not records:
            return ()
        if self._terminal is not None:
            raise SessionConflictError("run is already terminal")
        handle = self._active_handle()
        return await self.service.append_usage(
            self.principal,
            handle.run.run_id,
            handle.lease,
            tuple(records),
        )

    async def append_context_usage(
        self,
        snapshots: Sequence[ContextUsageSnapshot],
    ) -> tuple[ContextUsageSnapshot, ...]:
        if not snapshots:
            return ()
        if self._terminal is not None:
            raise SessionConflictError("run is already terminal")
        handle = self._active_handle()
        return await self.service.append_context_usage(
            self.principal,
            handle.run.run_id,
            handle.lease,
            tuple(snapshots),
        )

    async def append_messages(
        self,
        messages: Sequence[SessionMessageRecord],
    ) -> tuple[SessionMessageRecord, ...]:
        if not messages:
            return ()
        if self._terminal is not None:
            raise SessionConflictError("run is already terminal")
        handle = self._active_handle()
        return await self.service.append_run_messages(
            self.principal,
            handle.run.run_id,
            handle.lease,
            tuple(messages),
        )

    async def load_messages(self) -> tuple[SessionMessageRecord, ...]:
        return await self.service.load_run_messages(
            self.principal,
            self.run_id,
        )

    async def start_tool(
        self,
        call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        mutation: bool,
    ):
        handle = self._active_handle()
        return await self.service.start_run_tool(
            self.principal,
            handle.run.run_id,
            handle.lease,
            call_id,
            tool_name,
            arguments,
            mutation,
        )

    async def finish_tool(
        self,
        call_id: str,
        result: Any,
        ok: bool,
    ):
        handle = self._active_handle()
        return await self.service.finish_run_tool(
            self.principal,
            handle.run.run_id,
            handle.lease,
            call_id,
            result,
            ok,
        )

    async def load_tools(self):
        return await self.service.load_run_tools(
            self.principal,
            self.run_id,
        )

    async def heartbeat(self) -> HeartbeatResult:
        handle = self._active_handle()
        lease_seconds = float(self.service.config.runtime.lease_seconds)
        remaining = (handle.lease.expires_at - utc_now()).total_seconds()
        # Renew when half the lease is gone, or if already expired (same-holder revive).
        # Always-renewing every heartbeat fought event flush for the file lock and
        # produced portalocker AlreadyLocked → [Errno 35] under load.
        if remaining <= max(lease_seconds * 0.5, 30.0) or remaining <= 0:
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
        terminal_payload: dict[str, JsonValue] | None = None,
    ) -> TurnRecord:
        if self._terminal is not None:
            if isinstance(self._terminal, TurnRecord):
                return self._terminal
            raise SessionConflictError("run already ended without a committed turn")
        await self.flush()
        handle = self._active_handle()
        terminal_event = self._terminal_event("done", terminal_payload or {})
        self.terminal_event = terminal_event
        result = await self.service.commit_turn(
            self.principal,
            CommitTurnCommand(
                handle.run.run_id,
                handle.lease,
                turn,
                messages,
                usage,
                terminal_event,
            ),
        )
        self._terminal = result
        return result

    async def fail(self, error: dict[str, JsonValue] | None = None):
        if self._terminal is not None:
            return self._terminal
        try:
            await self.flush()
            handle = self._active_handle()
            terminal_event = self._terminal_event(
                "error",
                {
                    "message": str((error or {}).get("message") or "Run failed"),
                    "code": str((error or {}).get("code") or "agent_run_failed"),
                },
            )
            self.terminal_event = terminal_event
            result = await self.service.fail_run(
                self.principal,
                FinishRunCommand(
                    handle.run.run_id,
                    handle.lease,
                    error,
                    terminal_event,
                ),
            )
            self._terminal = result
            return result
        except SessionLeaseLostError:
            LOGGER.warning(
                "Cannot mark run failed; session lease already lost: run_id=%s session_id=%s",
                self.handle.run.run_id if self.handle is not None else None,
                self.session_id,
            )
            self._terminal = self.handle.run if self.handle is not None else True
            return self._terminal

    async def cancel(self, error: dict[str, JsonValue] | None = None):
        if self._terminal is not None:
            return self._terminal
        try:
            await self.flush()
            handle = self._active_handle()
            terminal_event = self._terminal_event(
                "error",
                {"message": "Run cancelled", "code": "cancelled"},
            )
            self.terminal_event = terminal_event
            result = await self.service.cancel_run(
                self.principal,
                FinishRunCommand(
                    handle.run.run_id,
                    handle.lease,
                    error,
                    terminal_event,
                ),
            )
            self._terminal = result
            return result
        except SessionLeaseLostError:
            LOGGER.warning(
                "Cannot mark run cancelled; session lease already lost: run_id=%s session_id=%s",
                self.handle.run.run_id if self.handle is not None else None,
                self.session_id,
            )
            self._terminal = self.handle.run if self.handle is not None else True
            return self._terminal

    async def request_cancel(self, run_id: str | None = None):
        target = run_id or self._active_handle().run.run_id
        return await self.service.request_cancel(self.principal, target)

    async def suspend(self) -> None:
        if self._terminal is not None:
            return
        await self.flush()
        handle = self._active_handle()
        await self.service.release_lease(self.principal, handle.lease)
        self._terminal = True

    async def read_events(self, *, after_seq: int = 0, limit: int = 100):
        handle = self._active_handle()
        return await self.service.read_events(self.principal, handle.run.run_id, after_seq=after_seq, limit=limit)

    def _terminal_event(
        self,
        event_type: str,
        values: dict[str, JsonValue],
    ) -> SessionEvent:
        handle = self._active_handle()
        sequence = self._next_sequence
        self._next_sequence += 1
        payload = {
            "type": event_type,
            "run_id": handle.run.run_id,
            "seq": sequence,
            "session_id": self.session_id,
            "schema_version": "2.0",
            "timestamp": utc_now().isoformat(),
            **values,
        }
        return SessionEvent(
            run_id=handle.run.run_id,
            sequence=sequence,
            event_type=event_type,
            payload=payload,
            lease_id=handle.lease.lease_id,
            fencing_token=handle.lease.fencing_token,
            idempotency_key=f"{handle.run.run_id}:event:{sequence}",
        )
