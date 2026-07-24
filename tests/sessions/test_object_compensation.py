import pytest

from dojoagents.sessions.blobs.file import FileBlobStore
from dojoagents.sessions.models import BlobMetadata, BlobWriteMetadata, SessionPrincipal
from tests.sessions.blob_contract import byte_stream


@pytest.mark.asyncio
async def test_blob_commit_is_idempotent_and_keeps_checksum(tmp_path):
    store = FileBlobStore(tmp_path / "blobs")
    principal = SessionPrincipal(user_id="alice")
    metadata = BlobWriteMetadata("session-1", "object-1", BlobMetadata("text/plain"))
    pending = await store.put(principal, byte_stream(b"abc"), metadata)

    first = await store.commit(principal, pending)
    second = await store.commit(principal, first)

    assert first == second
    assert first.checksum_sha256 == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
