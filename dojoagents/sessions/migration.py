from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from strands.types.session import SessionMessage

from dojoagents.sessions.compat.strands import strands_to_canonical
from dojoagents.sessions.errors import SessionNotFoundError
from dojoagents.sessions.models import (
    BlobMetadata,
    CheckpointWrite,
    SessionCreateSpec,
    SessionObjectSpec,
    SessionPrincipal,
    TurnRecord,
    UsageRecord,
    utc_now,
)
from dojoagents.sessions.run_coordinator import RunCoordinator
from dojoagents.sessions.service import SessionService


@dataclass(frozen=True)
class MigrationResult:
    session_count: int
    message_count: int
    object_count: int
    fingerprint: str
    already_migrated: bool = False
    dry_run: bool = False


def _source_fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid legacy JSON file: {path}") from exc


def _message_files(session_dir: Path) -> list[Path]:
    return sorted(
        session_dir.glob("agents/agent_*/messages/message_*.json"),
        key=lambda path: int(path.stem.rsplit("_", 1)[-1]),
    )


async def _bytes(data: bytes):
    yield data


class SessionMigrator:
    def __init__(self, service: SessionService) -> None:
        self.service = service

    @staticmethod
    def _principal_for(
        session_id: str,
        sidecar: dict[str, Any],
        owner_map: dict[str, SessionPrincipal],
        fallback_principal: SessionPrincipal | None,
    ) -> SessionPrincipal:
        if session_id in owner_map:
            return owner_map[session_id]
        user_id = str(sidecar.get("user_id") or "").strip()
        if user_id:
            return SessionPrincipal(user_id=user_id, tenant_id=str(sidecar.get("tenant_id") or "default"))
        if fallback_principal is not None:
            return fallback_principal
        raise ValueError(f"legacy session {session_id!r} has no owner; provide an explicit owner mapping or fallback")

    async def migrate(
        self,
        source_root: str | Path,
        *,
        owner_map: dict[str, SessionPrincipal] | None = None,
        fallback_principal: SessionPrincipal | None = None,
        dry_run: bool = False,
    ) -> MigrationResult:
        root = Path(source_root).expanduser().resolve()
        if not root.is_dir():
            raise ValueError(f"legacy session root does not exist: {root}")
        session_dirs = sorted(path for path in root.glob("session_*") if path.is_dir())
        mapping = dict(owner_map or {})
        prepared = []
        for session_dir in session_dirs:
            sidecar_path = session_dir / "dojo_session.json"
            sidecar = _read_json(sidecar_path) if sidecar_path.is_file() else {}
            if not isinstance(sidecar, dict):
                raise ValueError(f"legacy session sidecar must be a mapping: {sidecar_path}")
            session_id = str(sidecar.get("session_id") or session_dir.name.removeprefix("session_"))
            principal = self._principal_for(session_id, sidecar, mapping, fallback_principal)
            prepared.append((session_dir, session_id, sidecar, principal))
        fingerprint = _source_fingerprint(root)
        if dry_run:
            return MigrationResult(
                session_count=len(prepared),
                message_count=sum(len(_message_files(item[0])) for item in prepared),
                object_count=sum(1 for item in prepared for folder in ("inputs", "outputs", "artifacts") for path in (item[0] / folder).rglob("*") if path.is_file()),
                fingerprint=fingerprint,
                dry_run=True,
            )

        total_messages = 0
        total_objects = 0
        all_existing = bool(prepared)
        for session_dir, session_id, sidecar, principal in prepared:
            try:
                existing = await self.service.get_session(principal, session_id)
            except SessionNotFoundError:
                existing = None
            if existing is not None:
                if existing.metadata.get("migration_fingerprint") != fingerprint:
                    raise ValueError(f"destination session {session_id!r} exists with a different migration fingerprint")
                exported = await self.service.export_session(principal, session_id)
                total_messages += len(exported["messages"])
                total_objects += len(exported["objects"])
                continue
            all_existing = False
            session = await self.service.create_session(
                principal,
                SessionCreateSpec(
                    session_id=session_id,
                    harness_id=str(sidecar.get("harness_id") or "financial"),
                    harness_version=str(sidecar.get("harness_version") or "legacy"),
                    harness_state_schema_version=int(sidecar.get("harness_state_schema_version") or 1),
                    title=str(sidecar.get("title") or ""),
                    model=sidecar.get("model"),
                    metadata={"migration_fingerprint": fingerprint, "migration_source": "strands_file"},
                ),
            )
            messages = []
            for path in _message_files(session_dir):
                payload = _read_json(path)
                raw = SessionMessage.from_dict(payload).to_message()
                agent_id = path.parent.parent.name.removeprefix("agent_")
                sequence = int(path.stem.rsplit("_", 1)[-1])
                messages.append(
                    strands_to_canonical(
                        raw,
                        session_uid=session.session_uid,
                        session_id=session_id,
                        agent_id=agent_id,
                        sequence=sequence,
                    )
                )
            total_messages += len(messages)
            if messages:
                coordinator = RunCoordinator(
                    self.service,
                    principal,
                    session_id,
                    holder_id="session-migrator",
                    model=str(sidecar.get("model") or "legacy"),
                )
                run_id = f"migration-{fingerprint[:16]}"
                await coordinator.begin(run_id, idempotency_key=f"migration:{fingerprint}:{session_id}")
                user_message = next((message for message in messages if message.role == "user"), messages[0])
                assistant_message = next((message for message in reversed(messages) if message.role == "assistant"), messages[-1])
                now = utc_now()
                usage_records = []
                turns_path = session_dir / "dojo_turns.jsonl"
                if turns_path.is_file():
                    rows = [json.loads(line) for line in turns_path.read_text(encoding="utf-8").splitlines() if line.strip()]
                    for index, row in enumerate(rows, start=1):
                        usage = row.get("usage") if isinstance(row, dict) else {}
                        if isinstance(usage, dict):
                            usage_records.append(
                                UsageRecord(
                                    usage_id=f"migration-usage-{index}",
                                    session_uid=session.session_uid,
                                    run_id=run_id,
                                    provider="legacy",
                                    model=str(sidecar.get("model") or "legacy"),
                                    input_tokens=int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0),
                                    output_tokens=int(usage.get("output_tokens") or usage.get("completion_tokens") or 0),
                                    idempotency_key=f"migration:{fingerprint}:usage:{index}",
                                )
                            )
                await coordinator.commit(
                    TurnRecord(
                        session_uid=session.session_uid,
                        session_id=session_id,
                        run_id=run_id,
                        turn_id=f"migration-turn-{fingerprint[:16]}",
                        sequence=1,
                        input=user_message.content,
                        output=assistant_message.content,
                        created_at=now,
                        updated_at=now,
                    ),
                    messages=tuple(messages),
                    usage=tuple(usage_records),
                )
            for name in ("dojo_memory.json", "dojo_turns.jsonl"):
                path = session_dir / name
                if not path.is_file():
                    continue
                payload = _read_json(path) if path.suffix == ".json" else [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
                await self.service.put_checkpoint(
                    principal,
                    CheckpointWrite(session_id, "migration", name, payload),
                    expected_version=None,
                )
            writer = self.service.object_writer(principal, session_id)
            for folder in ("inputs", "outputs", "artifacts"):
                base = session_dir / folder
                if not base.is_dir():
                    continue
                for path in sorted(item for item in base.rglob("*") if item.is_file()):
                    relative = path.relative_to(base).as_posix()
                    await writer.write(
                        SessionObjectSpec(session_id, folder[:-1], relative, "application/octet-stream"),
                        _bytes(path.read_bytes()),
                        BlobMetadata("application/octet-stream", relative),
                    )
                    total_objects += 1
        return MigrationResult(
            session_count=len(prepared),
            message_count=total_messages,
            object_count=total_objects,
            fingerprint=fingerprint,
            already_migrated=all_existing,
        )
