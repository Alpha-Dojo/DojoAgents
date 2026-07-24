import json

import pytest
from strands.types.session import SessionMessage

from dojoagents.config.models import SessionsConfig
from dojoagents.sessions.blobs.file import FileBlobStore
from dojoagents.sessions.migration import SessionMigrator
from dojoagents.sessions.models import SessionPrincipal
from dojoagents.sessions.service import SessionService
from dojoagents.sessions.stores.file import FileSessionStore
from dojoagents.cli.main import build_parser


def _legacy_session(root, *, user_id=None):
    session = root / "session_legacy"
    messages = session / "agents" / "agent_dojo-agent" / "messages"
    messages.mkdir(parents=True)
    sidecar = {"session_id": "legacy", "title": "Legacy", "model": "old-model"}
    if user_id is not None:
        sidecar["user_id"] = user_id
    (session / "dojo_session.json").write_text(json.dumps(sidecar), encoding="utf-8")
    for sequence, raw in enumerate(
        [
            {"role": "user", "content": [{"text": "question"}]},
            {"role": "assistant", "content": [{"text": "answer"}]},
        ]
    ):
        payload = SessionMessage.from_message(raw, sequence).to_dict()
        (messages / f"message_{sequence}.json").write_text(json.dumps(payload), encoding="utf-8")
    (session / "dojo_turns.jsonl").write_text(
        json.dumps({"schema_version": 1, "turn_id": "old-turn", "usage": {"input_tokens": 2}}) + "\n",
        encoding="utf-8",
    )
    (session / "dojo_memory.json").write_text(json.dumps({"last_synced_message_id": 1}), encoding="utf-8")
    outputs = session / "outputs"
    outputs.mkdir()
    (outputs / "report.txt").write_text("artifact", encoding="utf-8")
    return session


async def _service(tmp_path):
    service = SessionService(
        store=FileSessionStore(tmp_path / "new-sessions", cursor_secret=b"secret"),
        blob_store=FileBlobStore(tmp_path / "new-blobs"),
        config=SessionsConfig(),
    )
    await service.startup()
    return service


@pytest.mark.asyncio
async def test_migration_requires_explicit_owner_when_legacy_owner_missing(tmp_path):
    source = tmp_path / "legacy"
    _legacy_session(source)
    migrator = SessionMigrator(await _service(tmp_path))

    with pytest.raises(ValueError, match="owner"):
        await migrator.migrate(source)


@pytest.mark.asyncio
async def test_migration_is_idempotent_and_retains_source_files(tmp_path):
    source = tmp_path / "legacy"
    session_dir = _legacy_session(source)
    service = await _service(tmp_path)
    migrator = SessionMigrator(service)
    principal = SessionPrincipal("mapped-user", "tenant-a")

    first = await migrator.migrate(source, fallback_principal=principal)
    second = await migrator.migrate(source, fallback_principal=principal)

    assert first.session_count == second.session_count == 1
    assert first.message_count == second.message_count == 2
    assert first.object_count == second.object_count == 1
    assert second.already_migrated is True
    assert (session_dir / "dojo_session.json").is_file()
    exported = await service.export_session(principal, "legacy")
    assert len(exported["messages"]) == 2
    assert len(exported["objects"]) == 1


def test_sessions_cli_exposes_non_destructive_migrate_and_principal_export():
    parser = build_parser()

    migrate = parser.parse_args(["sessions", "migrate", "--source", "/legacy", "--user-id", "alice", "--dry-run"])
    export = parser.parse_args(["sessions", "export", "--session-id", "s1", "--user-id", "alice", "--canonical"])

    assert migrate.sessions_command == "migrate"
    assert migrate.dry_run is True
    assert export.canonical is True
