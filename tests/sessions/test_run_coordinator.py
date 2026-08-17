import pytest

from dojoagents.config.models import SessionRuntimeConfig, SessionsConfig
from dojoagents.sessions.blobs.file import FileBlobStore
from dojoagents.sessions.errors import SessionConflictError
from dojoagents.sessions.models import (
    SessionCreateSpec,
    SessionMessageRecord,
    SessionPrincipal,
    TurnRecord,
    utc_now,
)
from dojoagents.sessions.run_coordinator import RunCoordinator
from dojoagents.sessions.service import SessionService
from dojoagents.sessions.stores.file import FileSessionStore


async def _service(tmp_path, *, batch_size=2):
    config = SessionsConfig(runtime=SessionRuntimeConfig(event_batch_size=batch_size, lease_seconds=90))
    service = SessionService(
        store=FileSessionStore(tmp_path / "sessions", cursor_secret=b"secret"),
        blob_store=FileBlobStore(tmp_path / "blobs"),
        config=config,
    )
    principal = SessionPrincipal("alice")
    await service.startup()
    session = await service.create_session(principal, SessionCreateSpec("s1", "financial", "1.0", 1))
    return service, principal, session


def _turn(session, run_id):
    now = utc_now()
    return TurnRecord(
        session.session_uid,
        session.session_id,
        run_id,
        f"turn-{run_id}",
        1,
        {"text": "input"},
        {"text": "output"},
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_run_coordinator_batches_events_and_commits_once(tmp_path):
    service, principal, session = await _service(tmp_path, batch_size=2)
    coordinator = RunCoordinator(service, principal, "s1", holder_id="worker-a", model="test-model")
    handle = await coordinator.begin("run-1", idempotency_key="idem-1")

    await coordinator.append_events([("content.delta", {"text": "a"})])
    assert (await service.read_events(principal, "run-1", after_seq=0, limit=10)).items == ()
    await coordinator.append_events([("content.delta", {"text": "b"})])
    events = (await service.read_events(principal, "run-1", after_seq=0, limit=10)).items
    assert [event.sequence for event in events] == [1, 2]
    assert all(event.fencing_token == handle.lease.fencing_token for event in events)

    message = SessionMessageRecord(
        session.session_uid,
        "s1",
        "dojo-agent",
        1,
        "assistant",
        {"text": "output"},
    )
    committed = await coordinator.commit(_turn(session, "run-1"), messages=(message,))
    assert committed.turn_id == "turn-run-1"
    assert (await service.get_run(principal, "run-1")).status == "completed"
    with pytest.raises(SessionConflictError):
        await service.request_cancel(principal, "run-1")


@pytest.mark.asyncio
async def test_run_state_machine_supports_fail_and_cancel(tmp_path):
    service, principal, _ = await _service(tmp_path)
    failed = RunCoordinator(service, principal, "s1", holder_id="worker-a", model="test-model")
    await failed.begin("run-fail", idempotency_key="idem-fail")
    first_failure = await failed.fail({"code": "provider_error"})
    assert first_failure.status == "failed"
    assert await failed.fail({"code": "provider_error"}) == first_failure

    cancelled = RunCoordinator(service, principal, "s1", holder_id="worker-b", model="test-model")
    await cancelled.begin("run-cancel", idempotency_key="idem-cancel")
    requested = await service.request_cancel(principal, "run-cancel")
    assert requested.status == "cancellation_requested"
    heartbeat = await cancelled.heartbeat()
    assert heartbeat.cancellation_requested is True
    terminal = await cancelled.cancel({"code": "user_cancelled"})
    assert terminal.status == "cancelled"
