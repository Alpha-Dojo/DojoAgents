"""S8 resource-bound tests.

These pin the *bounds* rather than the happy path: how many worker threads a
limiter really admits, how large a stream buffer can grow when the consumer
stalls, that a cancelled owner cannot orphan a child process, and that the
Dashboard run manager's teardown is a bounded, observable operation.
"""

from __future__ import annotations

import threading
import time

import anyio
import pytest

from dojoagents.utils.async_runtime import (
    FILE_IO_LIMIT,
    SyncWorkload,
    get_sync_limiter,
    run_sync_bounded,
)
from dojoagents.utils.blocking_portal import ThreadedBlockingPortal


# ── thread limiter effectiveness ────────────────────────────────────


@pytest.mark.anyio
async def test_file_io_limiter_caps_real_worker_threads() -> None:
    limiter = get_sync_limiter(SyncWorkload.FILE_IO)
    assert limiter.total_tokens == FILE_IO_LIMIT

    guard = threading.Lock()
    active = 0
    peak = 0

    def work() -> None:
        nonlocal active, peak
        with guard:
            active += 1
            peak = max(peak, active)
        time.sleep(0.02)
        with guard:
            active -= 1

    async def submit() -> None:
        await run_sync_bounded(work, abandon_on_cancel=True)

    async with anyio.create_task_group() as task_group:
        for _ in range(FILE_IO_LIMIT * 2):
            task_group.start_soon(submit)

    assert peak == FILE_IO_LIMIT


@pytest.mark.anyio
async def test_portal_bridge_bounds_the_threads_it_consumes() -> None:
    portal = ThreadedBlockingPortal(name="resource-bridge", bridge_concurrency=2)
    portal.start()
    try:
        guard = threading.Lock()
        active = 0
        peak = 0

        async def work() -> None:
            nonlocal active, peak
            with guard:
                active += 1
                peak = max(peak, active)
            await anyio.sleep(0.03)
            with guard:
                active -= 1

        async with anyio.create_task_group() as task_group:
            for _ in range(6):
                task_group.start_soon(portal.call_async, work)

        assert peak == 2
    finally:
        portal.shutdown()


# ── slow consumer memory ────────────────────────────────────────────


@pytest.mark.anyio
async def test_a_stalled_consumer_cannot_grow_the_buffer_past_capacity() -> None:
    capacity = 4
    send, receive = anyio.create_memory_object_stream[int](capacity)
    produced = 0

    async with send, receive:

        async def produce() -> None:
            nonlocal produced
            for index in range(capacity * 10):
                await send.send(index)
                produced += 1

        async with anyio.create_task_group() as task_group:
            task_group.start_soon(produce)
            await anyio.sleep(0.05)

            assert send.statistics().current_buffer_used <= capacity
            # The producer must be parked at the boundary, not piling up items.
            assert produced <= capacity + 1
            task_group.cancel_scope.cancel()


# ── background task accounting ──────────────────────────────────────


@pytest.mark.anyio
async def test_dashboard_run_manager_releases_its_loop_thread_on_shutdown() -> None:
    from dojoagents.agent.models import AgentResponse, ChatRequest
    from dojoagents.dashboard.agent_runs import AgentRunManager

    entered = threading.Event()

    class HoldAgent:
        async def run(self, request, *, event_sink=None):
            entered.set()
            try:
                await anyio.sleep(30)
            except anyio.get_cancelled_exc_class():
                raise
            return AgentResponse(content="done", session_id=request.session_id)

    portal = ThreadedBlockingPortal(name="resource-agent-runs")
    manager = AgentRunManager(portal=portal)
    request = ChatRequest(message="hold", user_id="u", session_id="resource-runs")

    record = await manager.create_run(request=request, model="test", agent=HoldAgent())
    started = await anyio.to_thread.run_sync(entered.wait, 5.0, abandon_on_cancel=True)
    assert started

    began = anyio.current_time()
    await manager.shutdown(timeout=5.0)
    elapsed = anyio.current_time() - began

    assert elapsed < 5.0
    assert record.status == "cancelled"
    assert record.settled
    assert portal.state == "closed"
    assert [t for t in threading.enumerate() if t.name.startswith("resource-agent-runs")] == []


@pytest.mark.anyio
async def test_dashboard_run_manager_rejects_runs_once_shutdown_began() -> None:
    from dojoagents.agent.models import ChatRequest
    from dojoagents.dashboard.agent_runs import AgentRunManager, PortalShutdownError

    class UnusedAgent:
        async def run(self, request, *, event_sink=None):  # pragma: no cover - never reached
            raise AssertionError("a run must not be started after shutdown")

    portal = ThreadedBlockingPortal(name="resource-late-runs")
    manager = AgentRunManager(portal=portal)
    await manager.shutdown(timeout=5.0)

    request = ChatRequest(message="late", user_id="u", session_id="resource-late")
    with pytest.raises(PortalShutdownError, match="no longer accepts new runs"):
        await manager.create_run(request=request, model="test", agent=UnusedAgent())


# ── child process reaping ───────────────────────────────────────────


@pytest.mark.anyio
async def test_child_process_is_reaped_when_its_owner_is_cancelled() -> None:
    from dojoagents.tools.processes import open_process, terminate_then_kill

    exit_codes: list[int | None] = []

    async def owner() -> None:
        process = await open_process(["sleep", "30"])
        try:
            await anyio.sleep(30)
        finally:
            # terminate_then_kill shields internally, so this still runs while
            # the owner is cancellation-pending.
            exit_codes.append(await terminate_then_kill(process, grace_seconds=1.0))

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(owner)
        await anyio.sleep(0.05)
        task_group.cancel_scope.cancel()

    # A recorded exit code proves the child was waited on, not orphaned.
    assert len(exit_codes) == 1
    assert exit_codes[0] is not None


@pytest.mark.anyio
async def test_terminate_then_kill_escalates_past_an_ignored_sigterm() -> None:
    from dojoagents.tools.processes import open_process, terminate_then_kill

    # ``exec`` keeps this a single process: the ignored SIGTERM disposition is
    # inherited, so the escalation is real and no orphaned ``sleep`` is left.
    process = await open_process(["sh", "-c", 'trap "" TERM; exec sleep 30'])
    try:
        code = await terminate_then_kill(process, grace_seconds=0.3)
    finally:
        if process.returncode is None:  # pragma: no cover - safety net
            process.kill()

    assert code is not None


@pytest.mark.anyio
async def test_run_process_is_cancellable_instead_of_hanging() -> None:
    from dojoagents.tools.processes import run_process

    with anyio.move_on_after(0.1) as scope:
        await run_process(["sleep", "30"])

    assert scope.cancelled_caught


# ── portal shutdown timing ──────────────────────────────────────────


@pytest.mark.anyio
async def test_portal_shutdown_is_bounded_even_with_a_running_task() -> None:
    portal = ThreadedBlockingPortal(name="resource-busy-portal")
    portal.start()

    async def never_finishes() -> None:
        await anyio.sleep(300)

    portal.start_task(never_finishes, name="resource-busy-task")

    began = anyio.current_time()
    await portal.ashutdown(timeout=5.0)
    elapsed = anyio.current_time() - began

    assert elapsed < 5.0
    assert portal.state == "closed"
