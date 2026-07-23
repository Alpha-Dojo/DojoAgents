from datetime import timedelta

import pytest

from dojoagents.config.models import SessionRuntimeConfig, SessionsConfig
from dojoagents.sessions.blobs.file import FileBlobStore
from dojoagents.sessions.errors import SessionLeaseLostError
from dojoagents.sessions.models import SessionCreateSpec, SessionPrincipal, utc_now
from dojoagents.sessions.run_coordinator import RunCoordinator
from dojoagents.sessions.service import SessionService
from dojoagents.sessions.stores.file import FileSessionStore


@pytest.mark.asyncio
async def test_cross_instance_failover_fences_old_coordinator(tmp_path, monkeypatch):
    import dojoagents.sessions.run_coordinator as coordinator_module
    import dojoagents.sessions.stores.file as file_module

    root = tmp_path / "sessions"
    config = SessionsConfig(runtime=SessionRuntimeConfig(event_batch_size=1, lease_seconds=10, heartbeat_seconds=3))
    first_service = SessionService(
        store=FileSessionStore(root, cursor_secret=b"secret"),
        blob_store=FileBlobStore(tmp_path / "blobs-a"),
        config=config,
    )
    second_service = SessionService(
        store=FileSessionStore(root, cursor_secret=b"secret"),
        blob_store=FileBlobStore(tmp_path / "blobs-b"),
        config=config,
    )
    principal = SessionPrincipal("alice")
    await first_service.startup()
    await second_service.startup()
    await first_service.create_session(principal, SessionCreateSpec("s1", "financial", "1.0", 1))
    started = utc_now()
    monkeypatch.setattr(file_module, "utc_now", lambda: started)
    monkeypatch.setattr(coordinator_module, "utc_now", lambda: started)
    first = RunCoordinator(first_service, principal, "s1", holder_id="worker-a", model="test-model")
    old_handle = await first.begin("run-1", idempotency_key="idem-1")

    advanced = started + timedelta(seconds=11)
    monkeypatch.setattr(file_module, "utc_now", lambda: advanced)
    monkeypatch.setattr(coordinator_module, "utc_now", lambda: advanced)
    second = RunCoordinator(second_service, principal, "s1", holder_id="worker-b", model="test-model")
    replacement = await second.begin("run-1", idempotency_key="idem-1")

    assert replacement.lease.fencing_token > old_handle.lease.fencing_token
    with pytest.raises(SessionLeaseLostError):
        await first.append_events([("content.delta", {"text": "stale"})])
    assert (await second.fail({"code": "worker_recovered"})).status == "failed"


@pytest.mark.asyncio
async def test_cancel_request_is_visible_across_service_instances(tmp_path):
    root = tmp_path / "sessions"
    config = SessionsConfig(runtime=SessionRuntimeConfig(event_batch_size=1))
    first_service = SessionService(
        store=FileSessionStore(root, cursor_secret=b"secret"),
        blob_store=FileBlobStore(tmp_path / "blobs-a"),
        config=config,
    )
    second_service = SessionService(
        store=FileSessionStore(root, cursor_secret=b"secret"),
        blob_store=FileBlobStore(tmp_path / "blobs-b"),
        config=config,
    )
    principal = SessionPrincipal("alice")
    await first_service.startup()
    await second_service.startup()
    await first_service.create_session(principal, SessionCreateSpec("s1", "financial", "1.0", 1))
    coordinator = RunCoordinator(first_service, principal, "s1", holder_id="worker-a", model="test-model")
    await coordinator.begin("run-1", idempotency_key="idem-1")

    await second_service.request_cancel(principal, "run-1")

    assert (await coordinator.heartbeat()).cancellation_requested is True
