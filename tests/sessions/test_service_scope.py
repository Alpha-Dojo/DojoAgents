import pytest

from dojoagents.config.models import SessionsConfig
from dojoagents.sessions.blobs.file import FileBlobStore
from dojoagents.sessions.errors import HarnessSessionIncompatibleError, SessionNotFoundError
from dojoagents.sessions.models import (
    CheckpointWrite,
    HistoryQuery,
    ObjectQuery,
    SessionCreateSpec,
    SessionListQuery,
    SessionPrincipal,
    TurnQuery,
    UsageQuery,
)
from dojoagents.sessions.service import SessionService
from dojoagents.sessions.stores.file import FileSessionStore


@pytest.mark.asyncio
async def test_service_scopes_every_session_surface_by_principal(tmp_path):
    service = SessionService(
        store=FileSessionStore(tmp_path / "sessions", cursor_secret=b"secret"),
        blob_store=FileBlobStore(tmp_path / "blobs"),
        config=SessionsConfig(),
    )
    alice = SessionPrincipal("alice", "tenant")
    bob = SessionPrincipal("bob", "tenant")
    spec = SessionCreateSpec("same-id", "financial", "1.0", 1)
    await service.startup()
    alice_session = await service.create_session(alice, spec)
    bob_session = await service.create_session(bob, spec)

    assert (await service.get_session(alice, "same-id")).session_uid == alice_session.session_uid
    assert (await service.get_session(bob, "same-id")).session_uid == bob_session.session_uid
    assert (await service.list_sessions(alice, SessionListQuery())).items == (alice_session,)
    assert (await service.history(alice, "same-id", HistoryQuery())).items == ()
    assert (await service.turns(alice, "same-id", TurnQuery())).items == ()
    assert (await service.usage(alice, "same-id", UsageQuery())).records == ()

    alice_checkpoint = await service.put_checkpoint(
        alice,
        CheckpointWrite("same-id", "memory", "watermark", {"turn": 1}),
        expected_version=None,
    )
    assert await service.get_checkpoint(alice, "same-id", "memory", "watermark") == alice_checkpoint
    assert await service.get_checkpoint(bob, "same-id", "memory", "watermark") is None
    with pytest.raises(SessionNotFoundError):
        await service.get_session(SessionPrincipal("stranger", "tenant"), "same-id")

    exported = await service.export_session(alice, "same-id")
    assert exported["session"]["owner"]["user_id"] == "alice"
    assert exported["checkpoints"][0]["payload"] == {"turn": 1}
    assert (await service.list_objects(alice, "same-id", ObjectQuery())).items == ()


class MigratingCodec:
    def migrate(self, state, *, from_version, from_schema_version, to_version, to_schema_version):
        return {**state, "migrated": f"{from_version}/{from_schema_version}->{to_version}/{to_schema_version}"}


@pytest.mark.asyncio
async def test_harness_session_handle_binds_namespace_and_migrates(tmp_path):
    service = SessionService(
        store=FileSessionStore(tmp_path / "sessions", cursor_secret=b"secret"),
        blob_store=FileBlobStore(tmp_path / "blobs"),
        config=SessionsConfig(),
    )
    principal = SessionPrincipal("alice")
    await service.startup()
    await service.create_session(principal, SessionCreateSpec("s1", "financial", "1.0", 1))
    original = service.harness_session(principal, "s1", "financial", "1.0", 1)
    saved = await original.save_state({"portfolio_id": "p-1"}, expected_version=None)
    assert saved.version == 1
    assert (await original.load_state()).state == {"portfolio_id": "p-1"}

    migrated = service.harness_session(
        principal,
        "s1",
        "financial",
        "2.0",
        2,
        codec=MigratingCodec(),
    )
    loaded = await migrated.load_state()
    assert loaded.state["migrated"] == "1.0/1->2.0/2"
    assert loaded.version == 2

    wrong = service.harness_session(principal, "s1", "support", "1.0", 1)
    with pytest.raises(HarnessSessionIncompatibleError):
        await wrong.load_state()
