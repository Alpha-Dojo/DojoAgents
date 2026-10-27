from __future__ import annotations

import threading

import anyio
import pytest

from dojoagents.utils.async_runtime import (
    CPU_WORK_LIMIT,
    FILE_IO_LIMIT,
    SDK_IO_LIMIT,
    OperationTimeoutError,
    SyncWorkload,
    gather_ordered,
    get_sync_limiter,
    is_cancelled_exception,
    operation_timeout,
    run_sync_bounded,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_sync_limiters_have_independent_declared_capacities() -> None:
    file_limiter = get_sync_limiter(SyncWorkload.FILE_IO)
    sdk_limiter = get_sync_limiter(SyncWorkload.SDK_IO)
    cpu_limiter = get_sync_limiter(SyncWorkload.CPU)

    assert file_limiter.total_tokens == FILE_IO_LIMIT
    assert sdk_limiter.total_tokens == SDK_IO_LIMIT
    assert cpu_limiter.total_tokens == CPU_WORK_LIMIT
    assert len({id(file_limiter), id(sdk_limiter), id(cpu_limiter)}) == 3


@pytest.mark.anyio
async def test_run_sync_bounded_supports_keyword_arguments() -> None:
    caller_thread = threading.get_ident()

    def combine(left: int, *, right: int) -> tuple[int, bool]:
        return left + right, threading.get_ident() != caller_thread

    assert await run_sync_bounded(combine, 2, right=3) == (5, True)


@pytest.mark.anyio
async def test_gather_ordered_retains_input_order_and_bounds_concurrency() -> None:
    active = 0
    peak = 0
    lock = anyio.Lock()

    def operation(value: int, delay: float):
        async def run() -> int:
            nonlocal active, peak
            async with lock:
                active += 1
                peak = max(peak, active)
            try:
                await anyio.sleep(delay)
                return value
            finally:
                async with lock:
                    active -= 1

        return run

    results = await gather_ordered(
        [operation(1, 0.03), operation(2, 0.01), operation(3, 0)],
        max_concurrency=2,
    )

    assert results == [1, 2, 3]
    assert peak == 2


@pytest.mark.anyio
async def test_gather_ordered_rejects_non_positive_limit() -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        await gather_ordered([], max_concurrency=0)


@pytest.mark.anyio
async def test_gather_ordered_can_preserve_partial_failures() -> None:
    async def succeed() -> int:
        return 7

    async def fail() -> int:
        raise ValueError("bad item")

    results = await gather_ordered([succeed, fail, succeed], return_exceptions=True)

    assert results[0] == 7
    assert isinstance(results[1], ValueError)
    assert results[2] == 7


@pytest.mark.anyio
async def test_gather_ordered_raises_original_error_after_siblings_finish() -> None:
    completed: list[str] = []

    async def fail() -> int:
        await anyio.sleep(0)
        raise ValueError("first input failed")

    async def finish() -> int:
        await anyio.sleep(0.01)
        completed.append("done")
        return 9

    with pytest.raises(ValueError, match="first input failed") as raised:
        await gather_ordered([fail, finish])

    assert not isinstance(raised.value, BaseExceptionGroup)
    assert completed == ["done"]


@pytest.mark.anyio
async def test_operation_timeout_converts_its_own_deadline() -> None:
    with pytest.raises(OperationTimeoutError, match="test operation timed out") as raised:
        with operation_timeout(0.01, operation="test operation"):
            await anyio.sleep(1)

    assert raised.value.operation == "test operation"
    assert raised.value.timeout_seconds == 0.01


@pytest.mark.anyio
async def test_operation_timeout_preserves_inner_timeout_error() -> None:
    with pytest.raises(TimeoutError, match="inner"):
        with operation_timeout(1, operation="outer"):
            raise TimeoutError("inner")


@pytest.mark.anyio
async def test_cancelled_exception_uses_active_backend_type() -> None:
    observed = False
    with anyio.CancelScope() as scope:
        scope.cancel()
        try:
            await anyio.lowlevel.checkpoint()
        except BaseException as exc:
            observed = is_cancelled_exception(exc)

    assert observed is True
