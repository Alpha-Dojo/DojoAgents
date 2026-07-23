from __future__ import annotations

import pytest

from dojoagents.config.models import SessionsConfig
from dojoagents.dashboard.sse import stream_persisted_run_events
from dojoagents.sessions.blobs.file import FileBlobStore
from dojoagents.sessions.models import SessionCreateSpec, SessionPrincipal
from dojoagents.sessions.run_coordinator import RunCoordinator
from dojoagents.sessions.service import SessionService
from dojoagents.sessions.stores.file import FileSessionStore


@pytest.mark.asyncio
async def test_second_service_replays_persisted_events_after_sequence(tmp_path):
    store = FileSessionStore(tmp_path / "sessions", cursor_secret=b"durable-sse")
    blobs = FileBlobStore(tmp_path / "blobs")
    await store.startup()
    await blobs.startup()
    writer = SessionService(store=store, blob_store=blobs, config=SessionsConfig())
    reader = SessionService(store=store, blob_store=blobs, config=SessionsConfig())
    principal = SessionPrincipal("alice")
    await writer.create_session(principal, SessionCreateSpec("s-1", "financial", "1.0.0", 1))
    coordinator = RunCoordinator(writer, principal, "s-1", holder_id="worker-1", model="test")
    await coordinator.begin("run-durable", idempotency_key="once")
    await coordinator.append_events((("delta", {"text": "one"}), ("delta", {"text": "two"})))
    await coordinator.fail({"code": "done-for-test"})

    replay = []
    async for event in stream_persisted_run_events(reader, principal, "run-durable", after_seq=1):
        replay.append(event)

    await blobs.shutdown()
    await store.shutdown()
    assert [event["sequence"] for event in replay] == [2]
    assert replay[0]["text"] == "two"
