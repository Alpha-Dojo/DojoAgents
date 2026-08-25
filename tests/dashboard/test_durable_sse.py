from __future__ import annotations

import pytest

from dojoagents.config.models import SessionsConfig
from dojoagents.dashboard.sse import stream_persisted_run_events
from dojoagents.sessions.blobs.file import FileBlobStore
from dojoagents.sessions.models import EventPage, RunRecord, SessionCreateSpec, SessionEvent, SessionPrincipal
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


@pytest.mark.asyncio
async def test_running_sse_retains_separate_event_and_status_reads():
    events = (SessionEvent("run-1", 1, "delta", {"text": "one"}, "lease", 1),)

    class RunningReader:
        def __init__(self):
            self.reads = 0
            self.status_reads = 0

        async def read_events(self, _principal, _run_id, *, after_seq, limit):
            assert limit == 200
            self.reads += 1
            if self.reads == 1:
                assert after_seq == 0
                return EventPage(events)
            assert after_seq == 1
            return EventPage(())

        async def get_run(self, _principal, _run_id):
            self.status_reads += 1
            return RunRecord("run-1", "session-1", "running" if self.status_reads == 1 else "completed", "test", "once")

    reader = RunningReader()
    replay = [
        event
        async for event in stream_persisted_run_events(
            reader,
            SessionPrincipal("alice"),
            "run-1",
            poll_seconds=0,
        )
    ]

    assert [event["sequence"] for event in replay] == [1]
    assert reader.reads == 3
    assert reader.status_reads == 2
