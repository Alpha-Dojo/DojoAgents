from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from dataclasses import asdict, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, TypeVar

import portalocker

from dojoagents.sessions.atomic import AtomicJsonStore, FileStoreError
from dojoagents.logging import LOGGER
from dojoagents.sessions.errors import (
    SessionConflictError,
    SessionDataCorruptError,
    SessionLeaseLostError,
    SessionNotFoundError,
)
from dojoagents.sessions.models import (
    BeginRunCommand,
    BlobRef,
    CheckpointRecord,
    CheckpointWrite,
    CommitTurnCommand,
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
    SessionMessageRecord,
    SessionObjectPage,
    SessionObjectRecord,
    SessionObjectSpec,
    SessionPage,
    SessionPatch,
    SessionPrincipal,
    SessionRecord,
    SessionScope,
    StoreHealth,
    TurnPage,
    TurnQuery,
    TurnRecord,
    UsageQuery,
    UsageRecord,
    UsageSummary,
    cursor_scope_hash,
    decode_cursor,
    encode_cursor,
    utc_now,
)

T = TypeVar("T")


def _encode(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return _encode(asdict(value))
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _encode(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, frozenset)):
        return [_encode(item) for item in value]
    return value


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value is not None else None


def _scope(data: dict[str, Any]) -> SessionScope:
    return SessionScope(**data)


def _session(data: dict[str, Any]) -> SessionRecord:
    return SessionRecord(
        **{
            **data,
            "owner": _scope(data["owner"]),
            "created_at": _dt(data["created_at"]),
            "updated_at": _dt(data["updated_at"]),
        }
    )


def _message(data: dict[str, Any]) -> SessionMessageRecord:
    return SessionMessageRecord(**{**data, "created_at": _dt(data["created_at"])})


def _run(data: dict[str, Any]) -> RunRecord:
    return RunRecord(
        **{
            **data,
            "created_at": _dt(data["created_at"]),
            "updated_at": _dt(data["updated_at"]),
            "finished_at": _dt(data.get("finished_at")),
        }
    )


def _event(data: dict[str, Any]) -> SessionEvent:
    return SessionEvent(**{**data, "created_at": _dt(data["created_at"])})


def _turn(data: dict[str, Any]) -> TurnRecord:
    return TurnRecord(
        **{
            **data,
            "tool_trace": tuple(data.get("tool_trace", [])),
            "created_at": _dt(data["created_at"]),
            "updated_at": _dt(data["updated_at"]),
        }
    )


def _usage(data: dict[str, Any]) -> UsageRecord:
    return UsageRecord(**{**data, "created_at": _dt(data["created_at"])})


def _checkpoint(data: dict[str, Any]) -> CheckpointRecord:
    return CheckpointRecord(
        **{
            **data,
            "created_at": _dt(data["created_at"]),
            "updated_at": _dt(data["updated_at"]),
        }
    )


def _blob(data: dict[str, Any]) -> BlobRef:
    return BlobRef(**{**data, "owner": _scope(data["owner"]), "created_at": _dt(data["created_at"])})


def _object(data: dict[str, Any]) -> SessionObjectRecord:
    blob = data.get("blob_ref")
    return SessionObjectRecord(
        **{
            **data,
            "blob_ref": _blob(blob) if blob else None,
            "created_at": _dt(data["created_at"]),
            "updated_at": _dt(data["updated_at"]),
        }
    )


def _lease(data: dict[str, Any]) -> SessionLease:
    return SessionLease(
        **{
            **data,
            "acquired_at": _dt(data["acquired_at"]),
            "expires_at": _dt(data["expires_at"]),
            "heartbeat_at": _dt(data["heartbeat_at"]),
        }
    )


class FileSessionStore:
    """Atomic JSON implementation of the backend-neutral SessionStore contract.

    External tenant/user/session identifiers are only used to derive a SHA-256
    owner index key; they are never joined into filesystem paths.
    """

    def __init__(self, root: str | Path, *, cursor_secret: bytes) -> None:
        if not cursor_secret:
            raise ValueError("cursor_secret must be non-empty")
        self.root = Path(root).expanduser().resolve()
        self.cursor_secret = cursor_secret
        self._documents = AtomicJsonStore(self.root, schema_version=1)
        self._state_path = self._documents.path_for("state")
        self._lock_path = self.root / ".session-store.lock"
        self._started = False

    @staticmethod
    def _empty_state() -> dict[str, Any]:
        return {
            "sessions": {},
            "owner_index": {},
            "messages": {},
            "runs": {},
            "events": {},
            "turns": {},
            "usage": {},
            "checkpoints": {},
            "objects": {},
            "leases": {},
            "lease_counters": {},
        }

    @staticmethod
    def _owner_key(principal: SessionPrincipal, session_id: str) -> str:
        raw = json.dumps(
            [principal.tenant_id, principal.user_id, session_id],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    @staticmethod
    def _run_key(principal: SessionPrincipal, run_id: str) -> str:
        raw = json.dumps(
            [principal.tenant_id, principal.user_id, run_id],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def _read_state_sync(self) -> dict[str, Any]:
        try:
            state = self._documents._read_sync(self._state_path, "state")
        except FileStoreError as exc:
            raise SessionDataCorruptError(str(exc)) from exc
        if state is None:
            return self._empty_state()
        if not isinstance(state, dict):
            raise SessionDataCorruptError("session store state must be a mapping")
        defaults = self._empty_state()
        defaults.update(state)
        return defaults

    def _transaction_sync(self, write: bool, callback: Callable[[dict[str, Any]], T]) -> T:
        self.root.mkdir(parents=True, exist_ok=True)
        with portalocker.Lock(str(self._lock_path), mode="a+", timeout=10):
            state = self._read_state_sync()
            result = callback(state)
            if write:
                self._documents._write_sync(self._state_path, state)
            return result

    async def _transaction(self, write: bool, callback: Callable[[dict[str, Any]], T]) -> T:
        return await asyncio.to_thread(self._transaction_sync, write, callback)

    def _session_for(self, state: dict[str, Any], principal: SessionPrincipal, session_id: str) -> SessionRecord:
        uid = state["owner_index"].get(self._owner_key(principal, session_id))
        data = state["sessions"].get(uid) if uid else None
        if data is None:
            raise SessionNotFoundError(f"session {session_id!r} not found")
        return _session(data)

    def _session_for_run(self, state: dict[str, Any], principal: SessionPrincipal, run_id: str) -> tuple[SessionRecord, RunRecord]:
        data = state["runs"].get(self._run_key(principal, run_id))
        if data is None:
            raise SessionNotFoundError(f"run {run_id!r} not found")
        run = _run(data)
        session = _session(state["sessions"][run.session_uid])
        if session.owner != SessionScope.from_principal(principal):
            raise SessionNotFoundError(f"run {run_id!r} not found")
        return session, run

    @staticmethod
    def _check_version(actual: int, expected: int) -> None:
        if actual != expected:
            raise SessionConflictError(f"expected version {expected}, got {actual}")

    @staticmethod
    def _checkpoint_key(namespace: str, key: str) -> str:
        return hashlib.sha256(f"{namespace}\0{key}".encode("utf-8")).hexdigest()

    @staticmethod
    def _validate_lease(state: dict[str, Any], session_uid: str, lease: SessionLease) -> SessionLease:
        current_data = state["leases"].get(session_uid)
        if current_data is None:
            raise SessionLeaseLostError("session lease is no longer active")
        current = _lease(current_data)
        if current.lease_id != lease.lease_id or current.fencing_token != lease.fencing_token:
            raise SessionLeaseLostError("session lease fencing token is stale")
        if current.expires_at <= utc_now():
            raise SessionLeaseLostError("session lease has expired")
        return current

    async def startup(self) -> None:
        def initialize(state: dict[str, Any]) -> None:
            return None

        await self._transaction(True, initialize)
        self._started = True

    async def health(self) -> StoreHealth:
        try:
            await self._transaction(False, lambda state: len(state["sessions"]))
            return StoreHealth(healthy=True, provider="file", schema_version=1)
        except Exception as exc:
            LOGGER.exception("FileSessionStore health check failed")
            return StoreHealth(healthy=False, provider="file", schema_version=1, detail=str(exc))

    async def shutdown(self) -> None:
        self._started = False

    async def create_session(self, principal: SessionPrincipal, spec: SessionCreateSpec) -> SessionRecord:
        def operation(state: dict[str, Any]) -> SessionRecord:
            owner_key = self._owner_key(principal, spec.session_id)
            if owner_key in state["owner_index"]:
                raise SessionConflictError(f"session {spec.session_id!r} already exists")
            now = utc_now()
            record = SessionRecord(
                session_uid=str(uuid.uuid4()),
                session_id=spec.session_id,
                owner=SessionScope.from_principal(principal),
                harness_id=spec.harness_id,
                harness_version=spec.harness_version,
                harness_state_schema_version=spec.harness_state_schema_version,
                title=spec.title,
                model=spec.model,
                metadata=spec.metadata,
                created_at=now,
                updated_at=now,
            )
            state["sessions"][record.session_uid] = _encode(record)
            state["owner_index"][owner_key] = record.session_uid
            return record

        return await self._transaction(True, operation)

    async def get_session(self, principal: SessionPrincipal, session_id: str) -> SessionRecord:
        return await self._transaction(False, lambda state: self._session_for(state, principal, session_id))

    async def list_sessions(self, principal: SessionPrincipal, query: SessionListQuery) -> SessionPage:
        def operation(state: dict[str, Any]) -> SessionPage:
            owner = SessionScope.from_principal(principal)
            records = [
                _session(data) for data in state["sessions"].values() if _scope(data["owner"]) == owner and (query.archived is None or bool(data["archived"]) == query.archived)
            ]
            records.sort(key=lambda item: (item.updated_at, item.session_uid), reverse=True)
            filters = {"archived": query.archived}
            scope_hash = cursor_scope_hash(principal.tenant_id, principal.user_id, filters)
            if query.cursor:
                payload = decode_cursor(query.cursor, self.cursor_secret, scope_hash)
                marker = (datetime.fromisoformat(payload["sort"][0]), str(payload["sort"][1]))
                records = [item for item in records if (item.updated_at, item.session_uid) < marker]
            page_items = records[: query.limit]
            next_cursor = None
            if len(records) > query.limit:
                last = page_items[-1]
                next_cursor = encode_cursor(
                    {"sort": [last.updated_at.isoformat(), last.session_uid], "direction": "next", "scope_hash": scope_hash},
                    self.cursor_secret,
                )
            return SessionPage(items=tuple(page_items), next_cursor=next_cursor)

        return await self._transaction(False, operation)

    async def update_session(self, principal: SessionPrincipal, session_id: str, patch: SessionPatch, expected_version: int) -> SessionRecord:
        def operation(state: dict[str, Any]) -> SessionRecord:
            current = self._session_for(state, principal, session_id)
            self._check_version(current.version, expected_version)
            updated = replace(
                current,
                title=current.title if patch.title is None else patch.title,
                archived=current.archived if patch.archived is None else patch.archived,
                metadata=current.metadata if patch.metadata is None else patch.metadata,
                version=current.version + 1,
                updated_at=utc_now(),
            )
            state["sessions"][current.session_uid] = _encode(updated)
            return updated

        return await self._transaction(True, operation)

    async def archive_session(self, principal: SessionPrincipal, session_id: str, expected_version: int) -> SessionRecord:
        return await self.update_session(principal, session_id, SessionPatch(archived=True), expected_version)

    async def load_history(self, principal: SessionPrincipal, session_id: str, query: HistoryQuery) -> HistoryPage:
        def operation(state: dict[str, Any]) -> HistoryPage:
            session = self._session_for(state, principal, session_id)
            records = [_message(item) for item in state["messages"].get(session.session_uid, [])]
            if query.agent_id:
                records = [item for item in records if item.agent_id == query.agent_id]
            records.sort(key=lambda item: item.sequence)
            if query.cursor:
                scope_hash = cursor_scope_hash(principal.tenant_id, principal.user_id, {"session_id": session_id, "agent_id": query.agent_id})
                marker = int(decode_cursor(query.cursor, self.cursor_secret, scope_hash)["sort"][0])
                records = [item for item in records if item.sequence > marker]
            page = records[: query.limit]
            next_cursor = None
            if len(records) > query.limit:
                scope_hash = cursor_scope_hash(principal.tenant_id, principal.user_id, {"session_id": session_id, "agent_id": query.agent_id})
                next_cursor = encode_cursor({"sort": [page[-1].sequence], "direction": "next", "scope_hash": scope_hash}, self.cursor_secret)
            return HistoryPage(tuple(page), next_cursor)

        return await self._transaction(False, operation)

    async def list_turns(self, principal: SessionPrincipal, session_id: str, query: TurnQuery) -> TurnPage:
        def operation(state: dict[str, Any]) -> TurnPage:
            session = self._session_for(state, principal, session_id)
            records = sorted((_turn(item) for item in state["turns"].get(session.session_uid, [])), key=lambda item: item.sequence)
            scope_hash = cursor_scope_hash(principal.tenant_id, principal.user_id, {"session_id": session_id})
            if query.cursor:
                marker = int(decode_cursor(query.cursor, self.cursor_secret, scope_hash)["sort"][0])
                records = [item for item in records if item.sequence > marker]
            page = records[: query.limit]
            next_cursor = None
            if len(records) > query.limit:
                next_cursor = encode_cursor({"sort": [page[-1].sequence], "direction": "next", "scope_hash": scope_hash}, self.cursor_secret)
            return TurnPage(tuple(page), next_cursor)

        return await self._transaction(False, operation)

    async def read_events(self, principal: SessionPrincipal, run_id: str, after_seq: int, limit: int) -> EventPage:
        def operation(state: dict[str, Any]) -> EventPage:
            self._session_for_run(state, principal, run_id)
            records = sorted(
                (_event(item) for item in state["events"].get(self._run_key(principal, run_id), [])),
                key=lambda item: item.sequence,
            )
            records = [item for item in records if item.sequence > after_seq]
            page = records[:limit]
            return EventPage(tuple(page), str(page[-1].sequence) if len(records) > limit and page else None)

        return await self._transaction(False, operation)

    async def get_usage(self, principal: SessionPrincipal, session_id: str, query: UsageQuery) -> UsageSummary:
        def operation(state: dict[str, Any]) -> UsageSummary:
            session = self._session_for(state, principal, session_id)
            records = [_usage(item) for item in state["usage"].get(session.session_uid, [])]
            if query.run_id:
                records = [item for item in records if item.run_id == query.run_id]
            if query.provider:
                records = [item for item in records if item.provider == query.provider]
            return UsageSummary(
                input_tokens=sum(item.input_tokens for item in records),
                output_tokens=sum(item.output_tokens for item in records),
                cache_tokens=sum(item.cache_tokens for item in records),
                cost=sum(item.cost or 0 for item in records),
                records=tuple(records),
            )

        return await self._transaction(False, operation)

    async def begin_run(self, principal: SessionPrincipal, command: BeginRunCommand) -> RunRecord:
        def operation(state: dict[str, Any]) -> RunRecord:
            session = self._session_for(state, principal, command.session_id)
            for data in state["runs"].values():
                existing = _run(data)
                if existing.session_uid == session.session_uid and existing.idempotency_key == command.idempotency_key:
                    return existing
            run_key = self._run_key(principal, command.run_id)
            if run_key in state["runs"]:
                raise SessionConflictError(f"run {command.run_id!r} already exists")
            now = utc_now()
            record = RunRecord(
                run_id=command.run_id,
                session_uid=session.session_uid,
                status="running",
                model=command.model,
                idempotency_key=command.idempotency_key,
                created_at=now,
                updated_at=now,
            )
            state["runs"][run_key] = _encode(record)
            return record

        return await self._transaction(True, operation)

    async def begin_run_with_lease(self, principal: SessionPrincipal, command: BeginRunCommand) -> RunHandle:
        def operation(state: dict[str, Any]) -> RunHandle:
            session = self._session_for(state, principal, command.session_id)
            existing = next(
                (_run(data) for data in state["runs"].values() if data["session_uid"] == session.session_uid and data["idempotency_key"] == command.idempotency_key),
                None,
            )
            run_key = self._run_key(principal, command.run_id)
            if existing is None:
                if run_key in state["runs"]:
                    raise SessionConflictError(f"run {command.run_id!r} already exists")
                now = utc_now()
                existing = RunRecord(
                    run_id=command.run_id,
                    session_uid=session.session_uid,
                    status="running",
                    model=command.model,
                    idempotency_key=command.idempotency_key,
                    created_at=now,
                    updated_at=now,
                )
                state["runs"][run_key] = _encode(existing)
            elif existing.run_id != command.run_id:
                raise SessionConflictError("run idempotency key is already bound to another run")
            elif existing.status not in {"running", "cancellation_requested"}:
                raise SessionConflictError(f"run is already {existing.status}")

            now = utc_now()
            current_data = state["leases"].get(session.session_uid)
            current = _lease(current_data) if current_data else None
            if current is not None and current.expires_at > now:
                if current.holder_id != command.holder_id:
                    raise SessionConflictError("session already has an active lease")
                lease = replace(
                    current,
                    expires_at=now + timedelta(seconds=command.lease_seconds),
                    heartbeat_at=now,
                )
            else:
                token = int(state["lease_counters"].get(session.session_uid, 0)) + 1
                state["lease_counters"][session.session_uid] = token
                lease = SessionLease(
                    lease_id=str(uuid.uuid4()),
                    session_uid=session.session_uid,
                    holder_id=command.holder_id,
                    fencing_token=token,
                    acquired_at=now,
                    expires_at=now + timedelta(seconds=command.lease_seconds),
                    heartbeat_at=now,
                )
            state["leases"][session.session_uid] = _encode(lease)
            return RunHandle(run=existing, lease=lease)

        return await self._transaction(True, operation)

    async def get_run(self, principal: SessionPrincipal, run_id: str) -> RunRecord:
        return await self._transaction(False, lambda state: self._session_for_run(state, principal, run_id)[1])

    async def list_runs(self, principal: SessionPrincipal, session_id: str) -> tuple[RunRecord, ...]:
        def operation(state: dict[str, Any]) -> tuple[RunRecord, ...]:
            session = self._session_for(state, principal, session_id)
            records = [_run(data) for data in state["runs"].values() if data["session_uid"] == session.session_uid]
            records.sort(key=lambda item: (item.created_at, item.run_id))
            return tuple(records)

        return await self._transaction(False, operation)

    async def request_cancel(self, principal: SessionPrincipal, run_id: str) -> RunRecord:
        def operation(state: dict[str, Any]) -> RunRecord:
            _, run = self._session_for_run(state, principal, run_id)
            if run.status == "cancellation_requested":
                return run
            if run.status != "running":
                raise SessionConflictError(f"run is already {run.status}")
            updated = replace(
                run,
                status="cancellation_requested",
                cancellation_requested=True,
                version=run.version + 1,
                updated_at=utc_now(),
            )
            state["runs"][self._run_key(principal, run_id)] = _encode(updated)
            return updated

        return await self._transaction(True, operation)

    async def append_events(self, principal: SessionPrincipal, run_id: str, events) -> None:
        def operation(state: dict[str, Any]) -> None:
            session, _ = self._session_for_run(state, principal, run_id)
            stored = state["events"].setdefault(self._run_key(principal, run_id), [])
            for event in events:
                if event.run_id != run_id:
                    raise SessionConflictError("event run_id does not match target run")
                current_lease_data = state["leases"].get(session.session_uid)
                if current_lease_data is None:
                    raise SessionLeaseLostError("session lease is no longer active")
                current_lease = _lease(current_lease_data)
                if event.lease_id != current_lease.lease_id or event.fencing_token != current_lease.fencing_token:
                    raise SessionLeaseLostError("event lease fencing token is stale")
                self._validate_lease(state, session.session_uid, current_lease)
                duplicate = next(
                    (item for item in stored if item["sequence"] == event.sequence or (event.idempotency_key and item.get("idempotency_key") == event.idempotency_key)),
                    None,
                )
                encoded = _encode(event)
                if duplicate is not None:
                    if duplicate != encoded:
                        raise SessionConflictError("event sequence or idempotency key conflict")
                    continue
                stored.append(encoded)
            stored.sort(key=lambda item: item["sequence"])

        await self._transaction(True, operation)

    async def commit_turn(self, principal: SessionPrincipal, command: CommitTurnCommand) -> TurnRecord:
        def operation(state: dict[str, Any]) -> TurnRecord:
            session, run = self._session_for_run(state, principal, command.run_id)
            stored_turns = state["turns"].setdefault(session.session_uid, [])
            duplicate = next((item for item in stored_turns if item["turn_id"] == command.turn.turn_id), None)
            if duplicate is not None:
                existing = _turn(duplicate)
                if existing != command.turn:
                    raise SessionConflictError("turn idempotency conflict")
                return existing
            self._validate_lease(state, session.session_uid, command.lease)
            if run.status != "running":
                raise SessionConflictError(f"run is already {run.status}")
            if command.turn.session_uid != session.session_uid or command.turn.run_id != run.run_id:
                raise SessionConflictError("turn does not belong to run session")
            if any(item["sequence"] == command.turn.sequence for item in stored_turns):
                raise SessionConflictError("turn sequence conflict")
            stored_turns.append(_encode(command.turn))
            stored_turns.sort(key=lambda item: item["sequence"])

            stored_messages = state["messages"].setdefault(session.session_uid, [])
            for message in command.messages:
                duplicate_message = next((item for item in stored_messages if item["agent_id"] == message.agent_id and item["sequence"] == message.sequence), None)
                encoded = _encode(message)
                if duplicate_message is not None and duplicate_message != encoded:
                    raise SessionConflictError("message sequence conflict")
                if duplicate_message is None:
                    stored_messages.append(encoded)
            stored_messages.sort(key=lambda item: (item["agent_id"], item["sequence"]))

            stored_usage = state["usage"].setdefault(session.session_uid, [])
            for usage in command.usage:
                duplicate_usage = next(
                    (item for item in stored_usage if item["usage_id"] == usage.usage_id or (usage.idempotency_key and item["idempotency_key"] == usage.idempotency_key)),
                    None,
                )
                encoded = _encode(usage)
                if duplicate_usage is not None and duplicate_usage != encoded:
                    raise SessionConflictError("usage idempotency conflict")
                if duplicate_usage is None:
                    stored_usage.append(encoded)

            now = utc_now()
            state["runs"][self._run_key(principal, run.run_id)] = _encode(replace(run, status="completed", version=run.version + 1, updated_at=now, finished_at=now))
            state["sessions"][session.session_uid] = _encode(
                replace(
                    session,
                    message_count=len(stored_messages),
                    turn_count=len(stored_turns),
                    version=session.version + 1,
                    updated_at=now,
                )
            )
            state["leases"].pop(session.session_uid, None)
            return command.turn

        return await self._transaction(True, operation)

    async def _finish_run(self, principal: SessionPrincipal, command: FinishRunCommand, status: str) -> RunRecord:
        def operation(state: dict[str, Any]) -> RunRecord:
            session, run = self._session_for_run(state, principal, command.run_id)
            if run.status == status:
                return run
            self._validate_lease(state, session.session_uid, command.lease)
            if run.status not in {"running", "cancellation_requested"}:
                raise SessionConflictError(f"run is already {run.status}")
            now = utc_now()
            updated = replace(run, status=status, error=command.error, version=run.version + 1, updated_at=now, finished_at=now)
            state["runs"][self._run_key(principal, run.run_id)] = _encode(updated)
            state["leases"].pop(session.session_uid, None)
            return updated

        return await self._transaction(True, operation)

    async def fail_run(self, principal: SessionPrincipal, command: FinishRunCommand) -> RunRecord:
        return await self._finish_run(principal, command, "failed")

    async def cancel_run(self, principal: SessionPrincipal, command: FinishRunCommand) -> RunRecord:
        return await self._finish_run(principal, command, "cancelled")

    async def get_checkpoint(self, principal: SessionPrincipal, session_id: str, namespace: str, key: str) -> CheckpointRecord | None:
        def operation(state: dict[str, Any]) -> CheckpointRecord | None:
            session = self._session_for(state, principal, session_id)
            data = state["checkpoints"].get(session.session_uid, {}).get(self._checkpoint_key(namespace, key))
            return _checkpoint(data) if data else None

        return await self._transaction(False, operation)

    async def list_checkpoints(self, principal: SessionPrincipal, session_id: str) -> tuple[CheckpointRecord, ...]:
        def operation(state: dict[str, Any]) -> tuple[CheckpointRecord, ...]:
            session = self._session_for(state, principal, session_id)
            records = [_checkpoint(data) for data in state["checkpoints"].get(session.session_uid, {}).values()]
            records.sort(key=lambda item: (item.namespace, item.key))
            return tuple(records)

        return await self._transaction(False, operation)

    async def put_checkpoint(self, principal: SessionPrincipal, checkpoint: CheckpointWrite, expected_version: int | None) -> CheckpointRecord:
        def operation(state: dict[str, Any]) -> CheckpointRecord:
            session = self._session_for(state, principal, checkpoint.session_id)
            records = state["checkpoints"].setdefault(session.session_uid, {})
            storage_key = self._checkpoint_key(checkpoint.namespace, checkpoint.key)
            current_data = records.get(storage_key)
            current = _checkpoint(current_data) if current_data else None
            if current is None:
                if expected_version is not None:
                    raise SessionConflictError("checkpoint does not exist at expected version")
                now = utc_now()
                record = CheckpointRecord(
                    session_uid=session.session_uid,
                    session_id=session.session_id,
                    namespace=checkpoint.namespace,
                    key=checkpoint.key,
                    payload=checkpoint.payload,
                    version=1,
                    created_at=now,
                    updated_at=now,
                )
            else:
                if expected_version is None:
                    raise SessionConflictError("checkpoint already exists")
                self._check_version(current.version, expected_version)
                record = replace(current, payload=checkpoint.payload, version=current.version + 1, updated_at=utc_now())
            records[storage_key] = _encode(record)
            return record

        return await self._transaction(True, operation)

    async def reserve_object(self, principal: SessionPrincipal, spec: SessionObjectSpec) -> SessionObjectRecord:
        def operation(state: dict[str, Any]) -> SessionObjectRecord:
            session = self._session_for(state, principal, spec.session_id)
            now = utc_now()
            record = SessionObjectRecord(
                object_id=str(uuid.uuid4()),
                session_uid=session.session_uid,
                session_id=session.session_id,
                kind=spec.kind,
                name=spec.name,
                content_type=spec.content_type,
                metadata=spec.metadata,
                created_at=now,
                updated_at=now,
            )
            state["objects"][record.object_id] = _encode(record)
            return record

        return await self._transaction(True, operation)

    def _object_for(self, state: dict[str, Any], principal: SessionPrincipal, object_id: str) -> SessionObjectRecord:
        data = state["objects"].get(object_id)
        if data is None:
            raise SessionNotFoundError(f"object {object_id!r} not found")
        record = _object(data)
        session = _session(state["sessions"][record.session_uid])
        if session.owner != SessionScope.from_principal(principal):
            raise SessionNotFoundError(f"object {object_id!r} not found")
        return record

    async def commit_object(self, principal: SessionPrincipal, object_id: str, blob_ref: BlobRef, expected_version: int) -> SessionObjectRecord:
        def operation(state: dict[str, Any]) -> SessionObjectRecord:
            current = self._object_for(state, principal, object_id)
            if current.status == "committed" and current.blob_ref == blob_ref:
                return current
            self._check_version(current.version, expected_version)
            if blob_ref.owner != SessionScope.from_principal(principal):
                raise SessionNotFoundError("blob not found")
            updated = replace(current, status="committed", blob_ref=blob_ref, version=current.version + 1, updated_at=utc_now())
            state["objects"][object_id] = _encode(updated)
            return updated

        return await self._transaction(True, operation)

    async def get_object(self, principal: SessionPrincipal, object_id: str) -> SessionObjectRecord:
        return await self._transaction(False, lambda state: self._object_for(state, principal, object_id))

    async def list_objects(self, principal: SessionPrincipal, session_id: str, query: ObjectQuery) -> SessionObjectPage:
        def operation(state: dict[str, Any]) -> SessionObjectPage:
            session = self._session_for(state, principal, session_id)
            records = [
                _object(item)
                for item in state["objects"].values()
                if item["session_uid"] == session.session_uid and (query.kind is None or item["kind"] == query.kind) and (query.status is None or item["status"] == query.status)
            ]
            records.sort(key=lambda item: (item.created_at, item.object_id))
            scope_hash = cursor_scope_hash(principal.tenant_id, principal.user_id, {"session_id": session_id, "kind": query.kind, "status": query.status})
            if query.cursor:
                payload = decode_cursor(query.cursor, self.cursor_secret, scope_hash)
                marker = (datetime.fromisoformat(payload["sort"][0]), str(payload["sort"][1]))
                records = [item for item in records if (item.created_at, item.object_id) > marker]
            page = records[: query.limit]
            next_cursor = None
            if len(records) > query.limit:
                last = page[-1]
                next_cursor = encode_cursor({"sort": [last.created_at.isoformat(), last.object_id], "direction": "next", "scope_hash": scope_hash}, self.cursor_secret)
            return SessionObjectPage(tuple(page), next_cursor)

        return await self._transaction(False, operation)

    async def mark_object_deleted(self, principal: SessionPrincipal, object_id: str, expected_version: int) -> SessionObjectRecord:
        def operation(state: dict[str, Any]) -> SessionObjectRecord:
            current = self._object_for(state, principal, object_id)
            if current.status == "deleted":
                return current
            self._check_version(current.version, expected_version)
            updated = replace(current, status="deleted", version=current.version + 1, updated_at=utc_now())
            state["objects"][object_id] = _encode(updated)
            return updated

        return await self._transaction(True, operation)

    async def acquire_lease(self, principal: SessionPrincipal, request: LeaseRequest) -> SessionLease:
        def operation(state: dict[str, Any]) -> SessionLease:
            session = self._session_for(state, principal, request.session_id)
            now = utc_now()
            current_data = state["leases"].get(session.session_uid)
            current = _lease(current_data) if current_data else None
            if current is not None and current.expires_at > now:
                if current.holder_id != request.holder_id:
                    raise SessionConflictError("session already has an active lease")
                renewed = replace(current, expires_at=now + timedelta(seconds=request.lease_seconds), heartbeat_at=now)
                state["leases"][session.session_uid] = _encode(renewed)
                return renewed
            token = int(state["lease_counters"].get(session.session_uid, 0)) + 1
            state["lease_counters"][session.session_uid] = token
            lease = SessionLease(
                lease_id=str(uuid.uuid4()),
                session_uid=session.session_uid,
                holder_id=request.holder_id,
                fencing_token=token,
                acquired_at=now,
                expires_at=now + timedelta(seconds=request.lease_seconds),
                heartbeat_at=now,
            )
            state["leases"][session.session_uid] = _encode(lease)
            return lease

        return await self._transaction(True, operation)

    async def renew_lease(self, principal: SessionPrincipal, lease: SessionLease) -> SessionLease:
        def operation(state: dict[str, Any]) -> SessionLease:
            session_data = state["sessions"].get(lease.session_uid)
            if session_data is None:
                raise SessionNotFoundError("session lease not found")
            session = _session(session_data)
            if session.owner != SessionScope.from_principal(principal):
                raise SessionNotFoundError("session lease not found")
            current = self._validate_lease(state, lease.session_uid, lease)
            now = utc_now()
            duration = max((lease.expires_at - lease.heartbeat_at).total_seconds(), 1)
            renewed = replace(current, expires_at=now + timedelta(seconds=duration), heartbeat_at=now)
            state["leases"][lease.session_uid] = _encode(renewed)
            return renewed

        return await self._transaction(True, operation)

    async def release_lease(self, principal: SessionPrincipal, lease: SessionLease) -> None:
        def operation(state: dict[str, Any]) -> None:
            session_data = state["sessions"].get(lease.session_uid)
            if session_data is None or _session(session_data).owner != SessionScope.from_principal(principal):
                raise SessionNotFoundError("session lease not found")
            if lease.session_uid not in state["leases"]:
                return
            self._validate_lease(state, lease.session_uid, lease)
            state["leases"].pop(lease.session_uid, None)

        await self._transaction(True, operation)
