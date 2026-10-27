"""Shared AnyIO concurrency primitives for DojoAgents.

This module intentionally stays small.  Business code should use AnyIO
directly for sleeps, task groups, streams, and cancellation scopes; the helpers
here cover only policies that must remain consistent across subsystems.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Iterator
from contextlib import contextmanager
from enum import Enum
from functools import partial
from typing import Any, TypeVar, cast

import anyio
from anyio.lowlevel import RunVar


T = TypeVar("T")

FILE_IO_LIMIT = 16
SDK_IO_LIMIT = 8
CPU_WORK_LIMIT = 4


class SyncWorkload(str, Enum):
    """Bounded worker-thread pools used by synchronous project operations."""

    FILE_IO = "file_io"
    SDK_IO = "sdk_io"
    CPU = "cpu"


_LIMITS = {
    SyncWorkload.FILE_IO: FILE_IO_LIMIT,
    SyncWorkload.SDK_IO: SDK_IO_LIMIT,
    SyncWorkload.CPU: CPU_WORK_LIMIT,
}
_LIMITERS = {
    workload: RunVar[anyio.CapacityLimiter](f"dojoagents_{workload.value}_limiter")
    for workload in SyncWorkload
}
_MISSING = object()


class OperationTimeoutError(TimeoutError):
    """A project operation exceeded its declared AnyIO deadline."""

    def __init__(self, operation: str, timeout_seconds: float) -> None:
        self.operation = operation
        self.timeout_seconds = timeout_seconds
        super().__init__(f"{operation} timed out after {timeout_seconds:g} seconds")


def get_sync_limiter(workload: SyncWorkload = SyncWorkload.FILE_IO) -> anyio.CapacityLimiter:
    """Return the current async context's limiter for a sync workload.

    Limiters are stored in AnyIO ``RunVar`` values instead of being constructed
    at import time, which keeps the module backend-safe and test-isolated.
    """

    run_var = _LIMITERS[workload]
    limiter = run_var.get(_MISSING)
    if limiter is _MISSING:
        limiter = anyio.CapacityLimiter(_LIMITS[workload])
        run_var.set(limiter)
    return cast(anyio.CapacityLimiter, limiter)


def file_io_limiter() -> anyio.CapacityLimiter:
    return get_sync_limiter(SyncWorkload.FILE_IO)


def sdk_io_limiter() -> anyio.CapacityLimiter:
    return get_sync_limiter(SyncWorkload.SDK_IO)


def cpu_work_limiter() -> anyio.CapacityLimiter:
    return get_sync_limiter(SyncWorkload.CPU)


async def run_sync_bounded(
    function: Callable[..., T],
    /,
    *args: Any,
    workload: SyncWorkload = SyncWorkload.FILE_IO,
    limiter: anyio.CapacityLimiter | None = None,
    abandon_on_cancel: bool = False,
    **kwargs: Any,
) -> T:
    """Run blocking work with a project-owned capacity limit.

    Keyword arguments are bound with ``functools.partial`` because AnyIO's
    ``run_sync`` forwards positional arguments only.  The default cancellation
    behavior waits for the worker to finish, which is required for writes and
    other operations that must not be abandoned midway.
    """

    call: Callable[..., T] = function
    call_args = args
    if kwargs:
        call = partial(function, *args, **kwargs)
        call_args = ()
    return await anyio.to_thread.run_sync(
        call,
        *call_args,
        abandon_on_cancel=abandon_on_cancel,
        limiter=limiter or get_sync_limiter(workload),
    )


async def gather_ordered(
    operations: Iterable[Callable[[], Awaitable[T]]],
    *,
    max_concurrency: int | None = None,
    return_exceptions: bool = False,
) -> list[T | Exception]:
    """Run async operation factories concurrently and retain input order.

    Operation factories are used instead of pre-created coroutine objects so a
    sibling failure cannot leave un-awaited coroutines behind.  An unhandled
    child exception is retained in its input slot while siblings finish.  The
    first exception in input order is then re-raised unless
    ``return_exceptions`` is enabled.  This preserves ``asyncio.gather``'s
    ordered error boundary without leaking an ``ExceptionGroup``.
    """

    factories = tuple(operations)
    if max_concurrency is not None and max_concurrency <= 0:
        raise ValueError("max_concurrency must be greater than zero")
    if not factories:
        return []

    results: list[object] = [_MISSING] * len(factories)
    semaphore = anyio.Semaphore(max_concurrency) if max_concurrency is not None else None

    async def run_one(index: int, factory: Callable[[], Awaitable[T]]) -> None:
        try:
            if semaphore is None:
                results[index] = await factory()
                return
            async with semaphore:
                results[index] = await factory()
        except Exception as exc:
            results[index] = exc

    async with anyio.create_task_group() as task_group:
        for index, factory in enumerate(factories):
            task_group.start_soon(run_one, index, factory)

    if any(result is _MISSING for result in results):
        raise RuntimeError("ordered operation completed without producing every result")
    if not return_exceptions:
        first_error = next((result for result in results if isinstance(result, Exception)), None)
        if first_error is not None:
            raise first_error
    return [cast(T | Exception, result) for result in results]


def is_cancelled_exception(exc: BaseException) -> bool:
    """Return whether ``exc`` is the active AnyIO backend's cancellation type.

    This helper must be called from an async context.
    """

    return isinstance(exc, anyio.get_cancelled_exc_class())


@contextmanager
def operation_timeout(
    timeout_seconds: float,
    *,
    operation: str = "operation",
) -> Iterator[anyio.CancelScope]:
    """Apply a hard timeout and convert only deadline expiry to a typed error."""

    scope: anyio.CancelScope | None = None
    try:
        with anyio.fail_after(timeout_seconds) as scope:
            yield scope
    except TimeoutError as exc:
        # Preserve TimeoutError raised by the operation itself.  Only translate
        # the error when this cancel scope actually reached its own deadline.
        if scope is None or not scope.cancel_called:
            raise
        raise OperationTimeoutError(operation, timeout_seconds) from exc


__all__ = [
    "CPU_WORK_LIMIT",
    "FILE_IO_LIMIT",
    "SDK_IO_LIMIT",
    "OperationTimeoutError",
    "SyncWorkload",
    "cpu_work_limiter",
    "file_io_limiter",
    "gather_ordered",
    "get_sync_limiter",
    "is_cancelled_exception",
    "operation_timeout",
    "run_sync_bounded",
    "sdk_io_limiter",
]
