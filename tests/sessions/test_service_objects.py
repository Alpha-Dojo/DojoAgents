import pytest

from dojoagents.config.models import SessionsConfig
from dojoagents.sessions.blobs.file import FileBlobStore
from dojoagents.sessions.errors import BlobStoreError, SessionNotFoundError
from dojoagents.sessions.models import BlobMetadata, SessionCreateSpec, SessionObjectSpec, SessionPrincipal
from dojoagents.sessions.service import SessionService
from dojoagents.sessions.stores.file import FileSessionStore
from tests.sessions.blob_contract import byte_stream, read_all


@pytest.mark.asyncio
async def test_object_writer_authorizes_metadata_before_opening_blob(tmp_path):
    blob_store = FileBlobStore(tmp_path / "blobs")
    service = SessionService(
        store=FileSessionStore(tmp_path / "sessions", cursor_secret=b"secret"),
        blob_store=blob_store,
        config=SessionsConfig(),
    )
    alice = SessionPrincipal("alice")
    bob = SessionPrincipal("bob")
    await service.startup()
    await service.create_session(alice, SessionCreateSpec("s1", "financial", "1.0", 1))
    writer = service.object_writer(alice, "s1")
    record = await writer.write(
        SessionObjectSpec("s1", "artifact", "report.txt", "text/plain"),
        byte_stream(b"report"),
        BlobMetadata("text/plain", "report.txt"),
    )

    assert record.status == "committed"
    assert record.blob_ref.state == "committed"
    assert await read_all(await writer.open(record.object_id)) == b"report"
    with pytest.raises(SessionNotFoundError):
        await service.object_writer(bob, "s1").open(record.object_id)


class FailCommitBlobStore(FileBlobStore):
    async def commit(self, principal, blob_ref):
        raise BlobStoreError("injected blob commit failure")


@pytest.mark.asyncio
async def test_object_writer_retains_pending_reference_when_blob_commit_fails(tmp_path):
    service = SessionService(
        store=FileSessionStore(tmp_path / "sessions", cursor_secret=b"secret"),
        blob_store=FailCommitBlobStore(tmp_path / "blobs"),
        config=SessionsConfig(),
    )
    principal = SessionPrincipal("alice")
    await service.startup()
    await service.create_session(principal, SessionCreateSpec("s1", "financial", "1.0", 1))
    writer = service.object_writer(principal, "s1")

    with pytest.raises(BlobStoreError, match="injected"):
        await writer.write(
            SessionObjectSpec("s1", "artifact", "report.txt", "text/plain"),
            byte_stream(b"report"),
            BlobMetadata("text/plain"),
        )

    [record] = (await service.list_objects(principal, "s1")).items
    assert record.blob_ref is not None
    assert record.blob_ref.state == "pending"
