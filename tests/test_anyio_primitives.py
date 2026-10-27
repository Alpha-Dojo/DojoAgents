"""S8 unit tests: the AnyIO primitive semantics the migration depends on.

Each test pins behaviour that a mechanical ``asyncio`` -> AnyIO port can get
subtly wrong: timeout scopes that leak cancellation, unbounded memory streams,
and limiter semantics.  All tests use the shared ``anyio_backend`` fixture from
``conftest`` so they run on the asyncio backend only.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import anyio
import pytest

from dojoagents.utils.async_runtime import run_sync_bounded


# ── fail_after / move_on_after ──────────────────────────────────────


@pytest.mark.anyio
async def test_fail_after_raises_timeout_and_marks_its_scope() -> None:
    with pytest.raises(TimeoutError) as raised:
        with anyio.fail_after(0.02) as scope:
            await anyio.sleep(5)

    assert scope.cancel_called
    # A timeout must surface as a plain TimeoutError, never a group.
    assert not isinstance(raised.value, BaseExceptionGroup)


@pytest.mark.anyio
async def test_fail_after_confines_cancellation_to_its_own_scope() -> None:
    with pytest.raises(TimeoutError):
        with anyio.fail_after(0.02):
            await anyio.sleep(5)

    # The caller is not cancellation-pending once the scope unwinds.
    await anyio.lowlevel.checkpoint()


@pytest.mark.anyio
async def test_move_on_after_suppresses_the_cancellation_and_reports_it() -> None:
    reached_the_end = False

    with anyio.move_on_after(0.02) as scope:
        await anyio.sleep(5)
        reached_the_end = True

    assert scope.cancel_called
    assert scope.cancelled_caught
    assert not reached_the_end


@pytest.mark.anyio
async def test_move_on_after_does_not_fire_when_the_body_finishes_in_time() -> None:
    with anyio.move_on_after(5) as scope:
        await anyio.sleep(0.01)

    assert not scope.cancel_called
    assert not scope.cancelled_caught


# ── Lock / Semaphore ────────────────────────────────────────────────


@pytest.mark.anyio
async def test_lock_serialises_the_critical_section() -> None:
    lock = anyio.Lock()
    active = 0
    peak = 0

    async def worker() -> None:
        nonlocal active, peak
        async with lock:
            active += 1
            peak = max(peak, active)
            await anyio.sleep(0.01)
            active -= 1

    async with anyio.create_task_group() as task_group:
        for _ in range(4):
            task_group.start_soon(worker)

    assert peak == 1


@pytest.mark.anyio
async def test_semaphore_bounds_concurrency_to_its_value() -> None:
    semaphore = anyio.Semaphore(2)
    active = 0
    peak = 0

    async def worker() -> None:
        nonlocal active, peak
        async with semaphore:
            active += 1
            peak = max(peak, active)
            await anyio.sleep(0.01)
            active -= 1

    async with anyio.create_task_group() as task_group:
        for _ in range(6):
            task_group.start_soon(worker)

    assert peak == 2


@pytest.mark.anyio
async def test_semaphore_from_async_runtime_bounds_gather_ordered() -> None:
    from functools import partial

    from dojoagents.utils.async_runtime import gather_ordered

    active = 0
    peak = 0

    def operation(index: int) -> Any:
        async def run() -> int:
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await anyio.sleep(0.01)
            active -= 1
            return index

        return run()

    results = await gather_ordered(
        [partial(operation, index) for index in range(5)],
        max_concurrency=2,
    )

    assert results == [0, 1, 2, 3, 4]
    assert peak == 2


# ── memory object streams and closing ───────────────────────────────


@pytest.mark.anyio
async def test_a_fast_producer_parks_at_the_declared_buffer_capacity() -> None:
    send, receive = anyio.create_memory_object_stream[int](2)
    async with send, receive:
        await send.send(1)
        await send.send(2)
        assert send.statistics().current_buffer_used == 2
        with pytest.raises(anyio.WouldBlock):
            send.send_nowait(3)

        produced_third = False

        async def produce() -> None:
            nonlocal produced_third
            await send.send(3)
            produced_third = True

        async with anyio.create_task_group() as task_group:
            task_group.start_soon(produce)
            await anyio.sleep(0.05)
            # The buffer is full, so the third send must be parked, not buffered.
            assert not produced_third
            assert send.statistics().current_buffer_used == 2
            assert await receive.receive() == 1

        assert produced_third


@pytest.mark.anyio
async def test_closing_the_sender_surfaces_end_of_stream() -> None:
    send, receive = anyio.create_memory_object_stream[int](1)
    async with receive:
        await send.send(7)
        await send.aclose()

        assert await receive.receive() == 7
        with pytest.raises(anyio.EndOfStream):
            await receive.receive()


@pytest.mark.anyio
async def test_closing_the_receiver_raises_broken_resource_on_send() -> None:
    send, receive = anyio.create_memory_object_stream[int](1)
    async with send:
        await receive.aclose()
        with pytest.raises(anyio.BrokenResourceError):
            await send.send(1)


# ── bounded sync work ───────────────────────────────────────────────


@pytest.mark.anyio
async def test_run_sync_bounded_honours_an_explicit_limiter() -> None:
    limiter = anyio.CapacityLimiter(2)
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
        await run_sync_bounded(work, limiter=limiter, abandon_on_cancel=True)

    async with anyio.create_task_group() as task_group:
        for _ in range(6):
            task_group.start_soon(submit)

    assert peak == 2


@pytest.mark.anyio
async def test_run_sync_bounded_runs_off_the_event_loop_thread() -> None:
    caller_thread = threading.get_ident()

    def identify() -> int:
        return threading.get_ident()

    assert await run_sync_bounded(identify) != caller_thread
