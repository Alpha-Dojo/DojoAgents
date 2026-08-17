from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import inspect
from typing import Any, Protocol

from dojoagents.config.models import SessionsConfig
from dojoagents.sessions.blob_store import BlobStore
from dojoagents.sessions.errors import HarnessSessionIncompatibleError, SessionsDisabledError
from dojoagents.sessions.models import (
    BlobMetadata,
    BlobWriteMetadata,
    BeginRunCommand,
    CheckpointRecord,
    CheckpointWrite,
    HistoryQuery,
    ObjectQuery,
    SessionCreateSpec,
    SessionListQuery,
    SessionObjectSpec,
    SessionPatch,
    SessionPrincipal,
    TurnQuery,
    UsageQuery,
    UsageRecord,
    SessionEvent,
    SessionLease,
    CommitTurnCommand,
    ContextUsageQuery,
    ContextUsageSnapshot,
    FinishRunCommand,
)
from dojoagents.sessions.store import SessionStore


class HarnessStateCodec(Protocol):
    def migrate(
        self,
        state: Any,
        *,
        from_version: str,
        from_schema_version: int,
        to_version: str,
        to_schema_version: int,
    ) -> Any: ...


@dataclass(frozen=True)
class TransientTurnContext:
    principal: SessionPrincipal
    session_id: str
    persistent: bool = False


@dataclass(frozen=True)
class HarnessStateSnapshot:
    state: Any
    version: int


def _jsonable(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return _jsonable(asdict(value))
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, frozenset)):
        return [_jsonable(item) for item in value]
    return value


class HarnessSessionHandle:
    def __init__(
        self,
        service: "SessionService",
        principal: SessionPrincipal,
        session_id: str,
        harness_id: str,
        harness_version: str,
        state_schema_version: int,
        codec: HarnessStateCodec | None,
    ) -> None:
        self._service = service
        self._principal = principal
        self._session_id = session_id
        self._harness_id = harness_id
        self._harness_version = harness_version
        self._state_schema_version = state_schema_version
        self._codec = codec
        self._namespace = f"harness:{harness_id}"

    async def _binding(self):
        record = await self._service.get_session(self._principal, self._session_id)
        if record.harness_id != self._harness_id:
            raise HarnessSessionIncompatibleError(f"session is bound to harness {record.harness_id!r}, not {self._harness_id!r}")
        return record

    async def load_state(self) -> HarnessStateSnapshot | None:
        binding = await self._binding()
        checkpoint = await self._service.get_checkpoint(
            self._principal,
            self._session_id,
            self._namespace,
            "state",
        )
        if checkpoint is None:
            if (binding.harness_version != self._harness_version or binding.harness_state_schema_version != self._state_schema_version) and self._codec is None:
                raise HarnessSessionIncompatibleError("harness version changed without a state codec")
            return None
        payload = checkpoint.payload
        if not isinstance(payload, dict) or "state" not in payload:
            raise HarnessSessionIncompatibleError("harness checkpoint envelope is invalid")
        stored_id = str(payload.get("harness_id") or binding.harness_id)
        if stored_id != self._harness_id:
            raise HarnessSessionIncompatibleError("harness checkpoint belongs to another harness")
        from_version = str(payload.get("harness_version") or binding.harness_version)
        from_schema = int(payload.get("state_schema_version") or binding.harness_state_schema_version)
        state = payload["state"]
        if from_version == self._harness_version and from_schema == self._state_schema_version:
            return HarnessStateSnapshot(state=state, version=checkpoint.version)
        if self._codec is None:
            raise HarnessSessionIncompatibleError("harness checkpoint requires an unavailable migration")
        migrated = self._codec.migrate(
            state,
            from_version=from_version,
            from_schema_version=from_schema,
            to_version=self._harness_version,
            to_schema_version=self._state_schema_version,
        )
        saved = await self.save_state(migrated, expected_version=checkpoint.version)
        return HarnessStateSnapshot(state=migrated, version=saved.version)

    async def save_state(self, state: Any, *, expected_version: int | None) -> CheckpointRecord:
        await self._binding()
        envelope = {
            "harness_id": self._harness_id,
            "harness_version": self._harness_version,
            "state_schema_version": self._state_schema_version,
            "state": state,
        }
        return await self._service.put_checkpoint(
            self._principal,
            CheckpointWrite(self._session_id, self._namespace, "state", envelope),
            expected_version,
        )


class SessionObjectWriter:
    def __init__(self, service: "SessionService", principal: SessionPrincipal, session_id: str) -> None:
        self._service = service
        self._principal = principal
        self._session_id = session_id

    async def write(self, spec: SessionObjectSpec, data, metadata: BlobMetadata):
        if spec.session_id != self._session_id:
            raise ValueError("object spec session_id does not match writer session")
        reserved = await self._service._store.reserve_object(self._principal, spec)
        pending = await self._service._blob_store.put(
            self._principal,
            data,
            BlobWriteMetadata(self._session_id, reserved.object_id, metadata),
        )
        linked = await self._service._store.commit_object(
            self._principal,
            reserved.object_id,
            pending,
            reserved.version,
        )
        committed_blob = await self._service._blob_store.commit(self._principal, pending)
        return await self._service._store.commit_object(
            self._principal,
            reserved.object_id,
            committed_blob,
            linked.version,
        )

    async def open(self, object_id: str):
        record = await self._service._store.get_object(self._principal, object_id)
        if record.session_id != self._session_id or record.blob_ref is None:
            from dojoagents.sessions.errors import SessionNotFoundError

            raise SessionNotFoundError("object not found")
        return await self._service._blob_store.open(self._principal, record.blob_ref)


class SessionService:
    def __init__(
        self,
        *,
        store: SessionStore,
        blob_store: BlobStore,
        config: SessionsConfig,
        result_projector: Any | None = None,
    ) -> None:
        self._store = store
        self._blob_store = blob_store
        self.config = config
        self._result_projector = result_projector

    def set_result_projector(self, projector: Any | None) -> None:
        """Attach a Harness-owned read projector without importing its domain."""

        self._result_projector = projector

    async def project_tool_results(self, results: Any, context: Any = None) -> dict[str, Any]:
        if self._result_projector is None:
            return {"viz_blocks": [], "artifacts": [], "resource_changes": []}
        callback = getattr(self._result_projector, "project_results", None)
        if callback is None:
            callback = getattr(self._result_projector, "project", self._result_projector)
        value = callback(results, context) if getattr(callback, "__name__", "") == "project_results" else callback(results)
        if inspect.isawaitable(value):
            value = await value
        return dict(value or {})

    def _enabled(self) -> None:
        if not self.config.enabled:
            raise SessionsDisabledError("session persistence is disabled")

    def require_persistence(self, capability: str) -> None:
        if not self.config.enabled:
            raise SessionsDisabledError(f"{capability} requires session persistence")

    def transient_turn(self, principal: SessionPrincipal, session_id: str) -> TransientTurnContext:
        if not session_id.strip():
            raise ValueError("session_id must be non-blank")
        return TransientTurnContext(principal=principal, session_id=session_id)

    async def startup(self) -> None:
        if not self.config.enabled:
            return
        await self._store.startup()
        await self._blob_store.startup()

    async def shutdown(self) -> None:
        if not self.config.enabled:
            return
        await self._blob_store.shutdown()
        await self._store.shutdown()

    async def create_session(self, principal: SessionPrincipal, spec: SessionCreateSpec):
        self._enabled()
        return await self._store.create_session(principal, spec)

    async def get_session(self, principal: SessionPrincipal, session_id: str):
        self._enabled()
        return await self._store.get_session(principal, session_id)

    async def list_sessions(self, principal: SessionPrincipal, query: SessionListQuery):
        self._enabled()
        return await self._store.list_sessions(principal, query)

    async def update_session(self, principal: SessionPrincipal, session_id: str, patch: SessionPatch, expected_version: int):
        self._enabled()
        return await self._store.update_session(principal, session_id, patch, expected_version)

    async def archive_session(self, principal: SessionPrincipal, session_id: str, expected_version: int):
        self._enabled()
        return await self._store.archive_session(principal, session_id, expected_version)

    async def history(self, principal: SessionPrincipal, session_id: str, query: HistoryQuery):
        self._enabled()
        return await self._store.load_history(principal, session_id, query)

    async def turns(self, principal: SessionPrincipal, session_id: str, query: TurnQuery):
        self._enabled()
        return await self._store.list_turns(principal, session_id, query)

    async def usage(self, principal: SessionPrincipal, session_id: str, query: UsageQuery):
        self._enabled()
        return await self._store.get_usage(principal, session_id, query)

    async def context_usage(
        self,
        principal: SessionPrincipal,
        session_id: str,
        query: ContextUsageQuery,
    ):
        self._enabled()
        return await self._store.get_context_usage(principal, session_id, query)

    async def begin_run_with_lease(self, principal: SessionPrincipal, command: BeginRunCommand):
        self._enabled()
        return await self._store.begin_run_with_lease(principal, command)

    async def get_run(self, principal: SessionPrincipal, run_id: str):
        self._enabled()
        return await self._store.get_run(principal, run_id)

    async def list_runs(self, principal: SessionPrincipal, session_id: str):
        self._enabled()
        return await self._store.list_runs(principal, session_id)

    async def request_cancel(self, principal: SessionPrincipal, run_id: str):
        self._enabled()
        return await self._store.request_cancel(principal, run_id)

    async def append_events(self, principal: SessionPrincipal, run_id: str, events: tuple[SessionEvent, ...]):
        self._enabled()
        return await self._store.append_events(principal, run_id, events)

    async def append_usage(
        self,
        principal: SessionPrincipal,
        run_id: str,
        lease: SessionLease,
        records: tuple[UsageRecord, ...],
    ) -> tuple[UsageRecord, ...]:
        self._enabled()
        return await self._store.append_usage(principal, run_id, lease, records)

    async def append_context_usage(
        self,
        principal: SessionPrincipal,
        run_id: str,
        lease: SessionLease,
        snapshots: tuple[ContextUsageSnapshot, ...],
    ) -> tuple[ContextUsageSnapshot, ...]:
        self._enabled()
        return await self._store.append_context_usage(
            principal,
            run_id,
            lease,
            snapshots,
        )

    async def read_events(self, principal: SessionPrincipal, run_id: str, *, after_seq: int, limit: int):
        self._enabled()
        return await self._store.read_events(principal, run_id, after_seq, limit)

    async def commit_turn(self, principal: SessionPrincipal, command: CommitTurnCommand):
        self._enabled()
        return await self._store.commit_turn(principal, command)

    async def fail_run(self, principal: SessionPrincipal, command: FinishRunCommand):
        self._enabled()
        return await self._store.fail_run(principal, command)

    async def cancel_run(self, principal: SessionPrincipal, command: FinishRunCommand):
        self._enabled()
        return await self._store.cancel_run(principal, command)

    async def renew_lease(self, principal: SessionPrincipal, lease):
        self._enabled()
        return await self._store.renew_lease(principal, lease)

    async def get_checkpoint(self, principal: SessionPrincipal, session_id: str, namespace: str, key: str):
        self._enabled()
        return await self._store.get_checkpoint(principal, session_id, namespace, key)

    async def put_checkpoint(self, principal: SessionPrincipal, checkpoint: CheckpointWrite, expected_version: int | None):
        self._enabled()
        return await self._store.put_checkpoint(principal, checkpoint, expected_version)

    async def list_objects(self, principal: SessionPrincipal, session_id: str, query: ObjectQuery | None = None):
        self._enabled()
        return await self._store.list_objects(principal, session_id, query or ObjectQuery())

    def object_writer(self, principal: SessionPrincipal, session_id: str) -> SessionObjectWriter:
        self._enabled()
        return SessionObjectWriter(self, principal, session_id)

    async def write_named_object(
        self,
        principal: SessionPrincipal,
        session_id: str,
        *,
        kind: str,
        name: str,
        content_type: str,
        data: bytes,
        metadata: dict[str, Any] | None = None,
    ):
        async def chunks():
            yield bytes(data)

        return await self.object_writer(principal, session_id).write(
            SessionObjectSpec(session_id, kind, name, content_type, metadata or {}),
            chunks(),
            BlobMetadata(content_type, filename=name, attributes=metadata or {}),
        )

    async def read_named_object(
        self,
        principal: SessionPrincipal,
        session_id: str,
        *,
        kind: str,
        name: str,
    ) -> tuple[Any, bytes]:
        page = await self.list_objects(
            principal,
            session_id,
            ObjectQuery(kind=kind, status="committed", limit=10_000),
        )
        matches = [record for record in page.items if record.name == name]
        if not matches:
            from dojoagents.sessions.errors import SessionNotFoundError

            raise SessionNotFoundError(f"session object not found: {name}")
        record = max(matches, key=lambda item: (item.created_at, item.object_id))
        stream = await self.object_writer(principal, session_id).open(record.object_id)
        return record, b"".join([chunk async for chunk in stream])

    def harness_session(
        self,
        principal: SessionPrincipal,
        session_id: str,
        harness_id: str,
        harness_version: str,
        state_schema_version: int,
        *,
        codec: HarnessStateCodec | None = None,
    ) -> HarnessSessionHandle:
        self._enabled()
        return HarnessSessionHandle(
            self,
            principal,
            session_id,
            harness_id,
            harness_version,
            state_schema_version,
            codec,
        )

    async def export_session(self, principal: SessionPrincipal, session_id: str) -> dict[str, Any]:
        self._enabled()
        session = await self._store.get_session(principal, session_id)
        history = await self._store.load_history(principal, session_id, HistoryQuery(limit=10_000))
        turns = await self._store.list_turns(principal, session_id, TurnQuery(limit=10_000))
        usage = await self._store.get_usage(principal, session_id, UsageQuery())
        context_usage = await self._store.get_context_usage(
            principal,
            session_id,
            ContextUsageQuery(include_history=True, limit=10_000),
        )
        runs = await self._store.list_runs(principal, session_id)
        events = []
        for run in runs:
            page = await self._store.read_events(principal, run.run_id, after_seq=0, limit=100_000)
            events.extend(page.items)
        checkpoints = await self._store.list_checkpoints(principal, session_id)
        objects = await self._store.list_objects(principal, session_id, ObjectQuery(limit=10_000))
        return {
            "schema_version": 1,
            "session": _jsonable(session),
            "messages": _jsonable(history.items),
            "turns": _jsonable(turns.items),
            "usage": _jsonable(usage.records),
            "context_usage": _jsonable(context_usage.history),
            "runs": _jsonable(runs),
            "events": _jsonable(events),
            "checkpoints": _jsonable(checkpoints),
            "objects": _jsonable(objects.items),
        }
