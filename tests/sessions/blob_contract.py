from __future__ import annotations

from dojoagents.sessions.models import BlobMetadata, BlobWriteMetadata, SessionPrincipal


async def byte_stream(*chunks: bytes):
    for chunk in chunks:
        yield chunk


async def read_all(stream) -> bytes:
    return b"".join([chunk async for chunk in stream])


async def assert_blob_store_contract(store) -> None:
    principal = SessionPrincipal(user_id="alice", tenant_id="tenant-a")
    metadata = BlobWriteMetadata(
        session_id="session-1",
        object_id="object-1",
        metadata=BlobMetadata(content_type="text/plain", filename="hello.txt"),
    )
    await store.startup()
    await store.startup()
    assert (await store.health()).healthy is True
    pending = await store.put(principal, byte_stream(b"hello", b" world"), metadata)
    assert pending.state == "pending"
    assert pending.size_bytes == 11
    assert await read_all(await store.open(principal, pending)) == b"hello world"
    committed = await store.commit(principal, pending)
    assert committed.state == "committed"
    assert await store.commit(principal, committed) == committed
    assert await store.stat(principal, committed) == committed
    await store.delete(principal, committed)
    await store.delete(principal, committed)
    await store.shutdown()
    await store.shutdown()
