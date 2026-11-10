from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import anyio
import pytest

from dojoagents.agent.session_run import CanonicalAgentRun, _DurableEventWriter, _RunHeartbeat
from dojoagents.agent.events import AgentEventSink
from dojoagents.sessions.errors import SessionLeaseLostError
from dojoagents.sessions.models import RunHandle, SessionPrincipal, utc_now
from dojoagents.sessions.run_coordinator import RunCoordinator


def coordinator(*, interval=0.1, lease_seconds=1):
    run = SimpleNamespace(run_id="run-test", cancellation_requested=False)
    service = SimpleNamespace(
        require_persistence=Mock(),
        config=SimpleNamespace(runtime=SimpleNamespace(heartbeat_seconds=interval, event_batch_size=20, lease_seconds=lease_seconds)),
        get_run=AsyncMock(return_value=run),
    )

    async def renew(_principal, _lease):
        return SimpleNamespace(expires_at=utc_now() + timedelta(seconds=lease_seconds))

    service.renew_lease = AsyncMock(side_effect=renew)
    value = RunCoordinator(service, SessionPrincipal("owner"), "session-test", holder_id="worker", model="test-model")
    value.handle = RunHandle(run=run, lease=SimpleNamespace(expires_at=utc_now() + timedelta(seconds=lease_seconds)))
    return value, service


@pytest.mark.anyio
async def test_every_heartbeat_renews_even_a_fresh_lease():
    value, service = coordinator(interval=20, lease_seconds=90)
    for _ in range(3):
        await value.heartbeat()
    assert service.renew_lease.await_count == service.get_run.await_count == 3


@pytest.mark.anyio
async def test_heartbeats_continue_while_chat_waits():
    value, service = coordinator()
    renewed = anyio.Event()
    original = service.renew_lease.side_effect

    async def renew(*args):
        result = await original(*args)
        if service.renew_lease.await_count >= 3:
            renewed.set()
        return result

    service.renew_lease.side_effect = renew
    owner = anyio.CancelScope()
    with anyio.fail_after(2):
        async with anyio.create_task_group() as group:
            heartbeat = _RunHeartbeat(value, owner, group)
            await renewed.wait()
            await heartbeat.close()
    assert service.renew_lease.await_count >= 3 and not owner.cancel_called


@pytest.mark.anyio
async def test_whole_heartbeat_timeout_includes_run_status_read():
    value, service = coordinator()

    async def hang(*_args):
        await anyio.sleep_forever()

    service.get_run.side_effect = hang
    owner = anyio.CancelScope()
    with anyio.fail_after(1):
        async with anyio.create_task_group() as group:
            heartbeat = _RunHeartbeat(value, owner, group)
            await heartbeat._done.wait()
    assert owner.cancel_called and service.get_run.await_count == service.renew_lease.await_count == 3
    assert isinstance(heartbeat._error, TimeoutError)


@pytest.mark.anyio
async def test_hanging_heartbeat_stops_at_remaining_lease_deadline():
    value, service = coordinator(interval=20, lease_seconds=0.04)

    async def hang(*_args):
        await anyio.sleep_forever()

    service.renew_lease.side_effect = hang
    owner = anyio.CancelScope()
    with anyio.fail_after(0.5):
        with pytest.raises(BaseExceptionGroup) as failure:
            async with anyio.create_task_group() as group:
                heartbeat = _RunHeartbeat(value, owner, group)
                await heartbeat._done.wait()
        assert isinstance(failure.value.exceptions[0], SessionLeaseLostError)
    assert service.renew_lease.await_count == 1 and owner.cancel_called
    assert isinstance(heartbeat._error, SessionLeaseLostError)


@pytest.mark.anyio
async def test_expired_lease_is_not_renewed_or_revived():
    value, service = coordinator(lease_seconds=-1)
    owner = anyio.CancelScope()
    with anyio.fail_after(0.5):
        with pytest.raises(BaseExceptionGroup) as failure:
            async with anyio.create_task_group() as group:
                heartbeat = _RunHeartbeat(value, owner, group)
                await heartbeat._done.wait()
        assert isinstance(failure.value.exceptions[0], SessionLeaseLostError)
    service.renew_lease.assert_not_awaited()
    assert owner.cancel_called and isinstance(heartbeat._error, SessionLeaseLostError)


@pytest.mark.anyio
async def test_transient_failure_recovers_within_lease():
    value, service = coordinator()
    original = service.renew_lease.side_effect
    recovered = anyio.Event()

    async def renew(*args):
        if service.renew_lease.await_count == 1:
            raise OSError("temporary store failure")
        recovered.set()
        return await original(*args)

    service.renew_lease.side_effect = renew
    owner = anyio.CancelScope()
    with anyio.fail_after(1):
        async with anyio.create_task_group() as group:
            heartbeat = _RunHeartbeat(value, owner, group)
            await recovered.wait()
            await heartbeat.close()
    assert service.renew_lease.await_count == 2 and not owner.cancel_called


@pytest.mark.anyio
async def test_hard_lease_loss_is_not_retried():
    value, service = coordinator()
    original = SessionLeaseLostError("fencing token changed")
    service.renew_lease.side_effect = original
    owner = anyio.CancelScope()
    with pytest.raises(BaseExceptionGroup) as failure:
        async with anyio.create_task_group() as group:
            heartbeat = _RunHeartbeat(value, owner, group)
            await heartbeat._done.wait()
    assert isinstance(failure.value.exceptions[0], SessionLeaseLostError)
    assert heartbeat._error is original and owner.cancel_called
    service.renew_lease.assert_awaited_once()


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["delta", "token_usage", "context_usage_snapshot"])
async def test_event_after_lease_loss_preserves_original_exception(kind):
    original = SessionLeaseLostError("expired original lease")
    value = SimpleNamespace(
        run_id="run-test",
        service=SimpleNamespace(config=SimpleNamespace(runtime=SimpleNamespace(event_batch_size=20))),
        append_events=AsyncMock(),
        flush=AsyncMock(side_effect=original),
    )
    sink = AgentEventSink(run_id="run-test", session_id="session-test")
    with anyio.fail_after(1):
        with pytest.raises(BaseExceptionGroup) as failure:
            async with anyio.create_task_group() as group:
                writer = _DurableEventWriter(value, sink, group)
                sink.delta("first")
                await writer._done.wait()
        assert failure.value.exceptions[0] is original
        with pytest.raises(SessionLeaseLostError) as caught:
            if kind == "delta":
                sink.delta("later")
            elif kind == "token_usage":
                sink.token_usage({})
            else:
                sink.context_usage_snapshot({}, state="actual")
        assert caught.value is original
        await writer.close()
        with pytest.raises(SessionLeaseLostError) as capacity_error:
            await writer._wait_for_capacity()
        assert capacity_error.value is original


@pytest.mark.anyio
async def test_lost_lease_never_attempts_a_cancel_terminal_write():
    original = SessionLeaseLostError("lease already lost")
    run = object.__new__(CanonicalAgentRun)
    run.heartbeat = SimpleNamespace(close=AsyncMock(), _error=original)
    run.event_writer = SimpleNamespace(close=AsyncMock(), _error=None)
    run.coordinator = SimpleNamespace(cancel=AsyncMock())
    with pytest.raises(SessionLeaseLostError) as caught:
        await run.cancel()
    assert caught.value is original
    run.coordinator.cancel.assert_not_awaited()


@pytest.mark.anyio
async def test_heartbeat_interval_does_not_add_request_duration(monkeypatch):
    value, service = coordinator(interval=20, lease_seconds=90)
    clock = iter((100.0, 103.0))
    monkeypatch.setattr(anyio, "current_time", lambda: next(clock))
    original_wait = anyio.move_on_after

    async def get_run(*_args):
        heartbeat._stop.set()
        return value.handle.run

    service.get_run.side_effect = get_run
    with patch("dojoagents.agent.session_run.anyio.move_on_after", wraps=original_wait) as wait:
        async with anyio.create_task_group() as group:
            heartbeat = _RunHeartbeat(value, anyio.CancelScope(), group)
            await heartbeat._done.wait()
    assert wait.call_args.args[0] == 17
    service.renew_lease.assert_awaited_once()


@pytest.mark.anyio
async def test_repeated_timeouts_share_the_remaining_lease_budget():
    value, service = coordinator(lease_seconds=0.13)
    expires = value.handle.lease.expires_at
    starts = []

    async def hang(*_args):
        starts.append(utc_now())
        await anyio.sleep_forever()

    service.renew_lease.side_effect = hang
    owner = anyio.CancelScope()
    with anyio.fail_after(0.5):
        with pytest.raises(BaseExceptionGroup) as failure:
            async with anyio.create_task_group() as group:
                heartbeat = _RunHeartbeat(value, owner, group)
                await heartbeat._done.wait()
        assert isinstance(failure.value.exceptions[0], SessionLeaseLostError)
    assert 2 <= len(starts) <= 3 and all(start < expires for start in starts)
    assert owner.cancel_called and isinstance(heartbeat._error, SessionLeaseLostError)
