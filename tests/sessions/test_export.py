import pytest

from dojoagents.config.models import SessionsConfig
from dojoagents.sessions.blobs.file import FileBlobStore
from dojoagents.sessions.export import SessionExporter
from dojoagents.sessions.models import BlobMetadata, SessionCreateSpec, SessionObjectSpec, SessionPrincipal
from dojoagents.sessions.service import SessionService
from dojoagents.sessions.stores.file import FileSessionStore
from tests.sessions.blob_contract import byte_stream


@pytest.mark.asyncio
async def test_export_is_versioned_backend_neutral_and_owner_scoped(tmp_path):
    sessions_root = tmp_path / "private-session-root"
    blobs_root = tmp_path / "private-blob-root"
    service = SessionService(
        store=FileSessionStore(sessions_root, cursor_secret=b"secret"),
        blob_store=FileBlobStore(blobs_root),
        config=SessionsConfig(),
    )
    alice = SessionPrincipal("alice", "tenant")
    bob = SessionPrincipal("bob", "tenant")
    await service.startup()
    await service.create_session(alice, SessionCreateSpec("same", "financial", "1.0", 1))
    await service.create_session(bob, SessionCreateSpec("same", "financial", "1.0", 1))
    await service.object_writer(alice, "same").write(
        SessionObjectSpec("same", "artifact", "report.txt", "text/plain"),
        byte_stream(b"alice artifact"),
        BlobMetadata("text/plain", "report.txt"),
    )

    bundle = await SessionExporter(service).export(alice, "same")

    assert bundle.manifest["schema_version"] == 1
    assert bundle.data["session"]["owner"]["user_id"] == "alice"
    assert list(bundle.blobs.values()) == [b"alice artifact"]
    serialized = str(bundle.manifest) + str(bundle.data)
    assert str(sessions_root) not in serialized
    assert str(blobs_root) not in serialized


@pytest.mark.asyncio
async def test_export_bundle_writes_safe_portable_directory(tmp_path):
    service = SessionService(
        store=FileSessionStore(tmp_path / "sessions", cursor_secret=b"secret"),
        blob_store=FileBlobStore(tmp_path / "blobs"),
        config=SessionsConfig(),
    )
    principal = SessionPrincipal("alice")
    await service.startup()
    await service.create_session(principal, SessionCreateSpec("s1", "financial", "1.0", 1))
    bundle = await SessionExporter(service).export(principal, "s1")

    result = await bundle.write_to(tmp_path / "export")

    assert (result / "manifest.json").is_file()
    assert (result / "session-data.json").is_file()
