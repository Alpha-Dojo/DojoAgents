from datetime import timedelta

import pytest

from dojoagents.sessions.blobs.file import FileBlobStore
from dojoagents.sessions.errors import BlobStoreError, SessionNotFoundError
from dojoagents.sessions.models import BlobMetadata, BlobWriteMetadata, SessionPrincipal, utc_now
from tests.sessions.blob_contract import assert_blob_store_contract, byte_stream


@pytest.mark.asyncio
async def test_file_blob_store_satisfies_contract(tmp_path):
    store = FileBlobStore(tmp_path / "blobs")

    await assert_blob_store_contract(store)


@pytest.mark.asyncio
async def test_file_blob_store_enforces_owner_scope(tmp_path):
    store = FileBlobStore(tmp_path / "blobs")
    alice = SessionPrincipal(user_id="alice", tenant_id="tenant-a")
    bob = SessionPrincipal(user_id="bob", tenant_id="tenant-a")
    metadata = BlobWriteMetadata("session-1", "object-1", BlobMetadata("text/plain"))
    blob = await store.put(alice, byte_stream(b"secret"), metadata)

    with pytest.raises(SessionNotFoundError):
        await store.stat(bob, blob)
    with pytest.raises(SessionNotFoundError):
        await store.open(bob, blob)
    with pytest.raises(SessionNotFoundError):
        await store.delete(bob, blob)


@pytest.mark.asyncio
async def test_pending_blob_and_interrupted_upload_are_collectable(tmp_path):
    store = FileBlobStore(tmp_path / "blobs")
    principal = SessionPrincipal(user_id="alice")
    metadata = BlobWriteMetadata("session-1", "object-1", BlobMetadata("application/octet-stream"))
    pending = await store.put(principal, byte_stream(b"pending"), metadata)

    async def interrupted():
        yield b"partial"
        raise RuntimeError("upload interrupted")

    with pytest.raises(BlobStoreError, match="interrupted"):
        await store.put(principal, interrupted(), metadata)

    removed = await store.collect_expired_pending(utc_now() + timedelta(days=1))
    assert removed == 2
    assert (await store.stat(principal, pending)).state == "deleted"


@pytest.mark.asyncio
async def test_soft_deleted_blob_is_retried_after_unlink_failure(tmp_path, monkeypatch):
    import dojoagents.sessions.blobs.file as file_module

    store = FileBlobStore(tmp_path / "blobs")
    principal = SessionPrincipal(user_id="alice")
    metadata = BlobWriteMetadata("session-1", "object-1", BlobMetadata("text/plain"))
    blob = await store.put(principal, byte_stream(b"retry"), metadata)
    committed = await store.commit(principal, blob)
    original_unlink = file_module._unlink_if_exists

    def fail_unlink(path):
        raise OSError("disk busy")

    monkeypatch.setattr(file_module, "_unlink_if_exists", fail_unlink)
    with pytest.raises(BlobStoreError, match="disk busy"):
        await store.delete(principal, committed)
    monkeypatch.setattr(file_module, "_unlink_if_exists", original_unlink)

    assert await store.retry_soft_deleted(limit=10) == 1
    assert (await store.stat(principal, committed)).state == "deleted"
