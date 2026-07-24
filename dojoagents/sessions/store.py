from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from dojoagents.sessions.models import (
    BeginRunCommand,
    CheckpointRecord,
    CheckpointWrite,
    CommitTurnCommand,
    ContextUsageQuery,
    ContextUsageSnapshot,
    ContextUsageSummary,
    EventPage,
    FinishRunCommand,
    HistoryPage,
    HistoryQuery,
    LeaseRequest,
    ObjectQuery,
    RunRecord,
    RunHandle,
    SessionCreateSpec,
    SessionEvent,
    SessionLease,
    SessionListQuery,
    SessionObjectPage,
    SessionObjectRecord,
    SessionObjectSpec,
    SessionPage,
    SessionPatch,
    SessionPrincipal,
    SessionRecord,
    StoreHealth,
    TurnPage,
    TurnQuery,
    TurnRecord,
    UsageQuery,
    UsageRecord,
    UsageSummary,
    BlobRef,
)

SESSION_STORE_METHODS = (
    "startup",
    "health",
    "shutdown",
    "create_session",
    "get_session",
    "list_sessions",
    "update_session",
    "archive_session",
    "load_history",
    "list_turns",
    "read_events",
    "get_usage",
    "get_context_usage",
    "begin_run",
    "begin_run_with_lease",
    "get_run",
    "list_runs",
    "request_cancel",
    "append_events",
    "append_usage",
    "append_context_usage",
    "commit_turn",
    "fail_run",
    "cancel_run",
    "get_checkpoint",
    "list_checkpoints",
    "put_checkpoint",
    "reserve_object",
    "commit_object",
    "get_object",
    "list_objects",
    "mark_object_deleted",
    "acquire_lease",
    "renew_lease",
    "release_lease",
)


@runtime_checkable
class SessionStore(Protocol):
    async def startup(self) -> None: ...

    async def health(self) -> StoreHealth: ...

    async def shutdown(self) -> None: ...

    async def create_session(self, principal: SessionPrincipal, spec: SessionCreateSpec) -> SessionRecord: ...

    async def get_session(self, principal: SessionPrincipal, session_id: str) -> SessionRecord: ...

    async def list_sessions(self, principal: SessionPrincipal, query: SessionListQuery) -> SessionPage: ...

    async def update_session(
        self,
        principal: SessionPrincipal,
        session_id: str,
        patch: SessionPatch,
        expected_version: int,
    ) -> SessionRecord: ...

    async def archive_session(
        self,
        principal: SessionPrincipal,
        session_id: str,
        expected_version: int,
    ) -> SessionRecord: ...

    async def load_history(
        self,
        principal: SessionPrincipal,
        session_id: str,
        query: HistoryQuery,
    ) -> HistoryPage: ...

    async def list_turns(
        self,
        principal: SessionPrincipal,
        session_id: str,
        query: TurnQuery,
    ) -> TurnPage: ...

    async def read_events(
        self,
        principal: SessionPrincipal,
        run_id: str,
        after_seq: int,
        limit: int,
    ) -> EventPage: ...

    async def get_usage(
        self,
        principal: SessionPrincipal,
        session_id: str,
        query: UsageQuery,
    ) -> UsageSummary: ...

    async def get_context_usage(
        self,
        principal: SessionPrincipal,
        session_id: str,
        query: ContextUsageQuery,
    ) -> ContextUsageSummary: ...

    async def begin_run(self, principal: SessionPrincipal, command: BeginRunCommand) -> RunRecord: ...

    async def begin_run_with_lease(self, principal: SessionPrincipal, command: BeginRunCommand) -> RunHandle: ...

    async def get_run(self, principal: SessionPrincipal, run_id: str) -> RunRecord: ...

    async def list_runs(self, principal: SessionPrincipal, session_id: str) -> tuple[RunRecord, ...]: ...

    async def request_cancel(self, principal: SessionPrincipal, run_id: str) -> RunRecord: ...

    async def append_events(
        self,
        principal: SessionPrincipal,
        run_id: str,
        events: Sequence[SessionEvent],
    ) -> None: ...

    async def append_usage(
        self,
        principal: SessionPrincipal,
        run_id: str,
        lease: SessionLease,
        records: Sequence[UsageRecord],
    ) -> tuple[UsageRecord, ...]: ...

    async def append_context_usage(
        self,
        principal: SessionPrincipal,
        run_id: str,
        lease: SessionLease,
        snapshots: Sequence[ContextUsageSnapshot],
    ) -> tuple[ContextUsageSnapshot, ...]: ...

    async def commit_turn(self, principal: SessionPrincipal, command: CommitTurnCommand) -> TurnRecord: ...

    async def fail_run(self, principal: SessionPrincipal, command: FinishRunCommand) -> RunRecord: ...

    async def cancel_run(self, principal: SessionPrincipal, command: FinishRunCommand) -> RunRecord: ...

    async def get_checkpoint(
        self,
        principal: SessionPrincipal,
        session_id: str,
        namespace: str,
        key: str,
    ) -> CheckpointRecord | None: ...

    async def list_checkpoints(
        self,
        principal: SessionPrincipal,
        session_id: str,
    ) -> tuple[CheckpointRecord, ...]: ...

    async def put_checkpoint(
        self,
        principal: SessionPrincipal,
        checkpoint: CheckpointWrite,
        expected_version: int | None,
    ) -> CheckpointRecord: ...

    async def reserve_object(
        self,
        principal: SessionPrincipal,
        spec: SessionObjectSpec,
    ) -> SessionObjectRecord: ...

    async def commit_object(
        self,
        principal: SessionPrincipal,
        object_id: str,
        blob_ref: BlobRef,
        expected_version: int,
    ) -> SessionObjectRecord: ...

    async def get_object(self, principal: SessionPrincipal, object_id: str) -> SessionObjectRecord: ...

    async def list_objects(
        self,
        principal: SessionPrincipal,
        session_id: str,
        query: ObjectQuery,
    ) -> SessionObjectPage: ...

    async def mark_object_deleted(
        self,
        principal: SessionPrincipal,
        object_id: str,
        expected_version: int,
    ) -> SessionObjectRecord: ...

    async def acquire_lease(self, principal: SessionPrincipal, request: LeaseRequest) -> SessionLease: ...

    async def renew_lease(self, principal: SessionPrincipal, lease: SessionLease) -> SessionLease: ...

    async def release_lease(self, principal: SessionPrincipal, lease: SessionLease) -> None: ...
