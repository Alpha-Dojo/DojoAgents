"""Detached background tasks — the second sanctioned asyncio boundary.

AnyIO is a structured-concurrency library: every task must be owned by a task
group whose lifetime encloses it, and the group's exit waits for (or cancels)
its children.  One subsystem genuinely needs the opposite behaviour:

:mod:`dojoagents.tools.process_registry` keeps one stdout drainer and one reaper
per *background* child process.  The ``terminal`` tool call that spawns the child
returns immediately, and the enclosing request frequently finishes long before
the child does, so the drainer/reaper must outlive the scope that created them
while never keeping it open.

AnyIO exposes no public fire-and-forget primitive, and every scope-safe
alternative was measured to be unusable (probe results, anyio 4.15.1):

* ``anyio.to_thread.run_sync(..., abandon_on_cancel=True)`` still *awaits* the
  worker, so it cannot be used as a launcher;
* ``anyio.from_thread.run()`` called from such an abandoned worker is still bound
  to the cancelling task's cancel scope — the coroutine was cancelled together
  with the caller instead of surviving it;
* entering a registry-owned ``TaskGroup`` with ``__aenter__`` from a short-lived
  task raises ``RuntimeError: Attempted to exit a cancel scope that isn't the
  current tasks's current cancel scope`` the moment that task returns.

This module therefore keeps the single escape hatch in one auditable place.  It
mirrors :mod:`dojoagents.tools.af_unix_asyncio_compat`, is the only other module
allowed to import ``asyncio``, and is registered in ``PERMANENT_ASYNCIO_ALLOWLIST``
(``tests/test_asyncio_boundaries.py``) and ``PRESERVE_ALLOWLIST``
(``.agents/scripts/audit_asyncio_usage.py``).

Removal condition
-----------------

Delete this module once AnyIO exposes a public, scope-safe detached-task
primitive (a supported replacement for ``lowlevel.spawn_system_task``, absent in
4.15.1).  Until then the retention rules in
``docs/site/*/design/async-runtime.md`` apply: no business logic here, no
``asyncio`` type in the public signatures, and no caller may take ownership of
the underlying task.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any, TypeVar

from dojoagents.logging import LOGGER

T = TypeVar("T")

_detached: set[asyncio.Task[Any]] = set()


def start_detached(coro: Coroutine[Any, Any, T], *, name: str | None = None) -> None:
    """Schedule ``coro`` on the running event loop, detached from every scope.

    The task is not owned by any task group, so it survives the exit or
    cancellation of the task that started it.  Failures are logged instead of
    being propagated, because no structured parent exists to receive them.

    Deliberately returns ``None``: the task handle stays private so no
    ``asyncio`` type leaks into a public signature and no caller can take
    ownership of a task this module is responsible for draining.  Use
    :func:`pending_detached` / :func:`drain_detached` to observe and await them.
    """
    task = asyncio.get_running_loop().create_task(coro, name=name)
    _detached.add(task)
    task.add_done_callback(_discard_finished)


def pending_detached() -> int:
    """Number of detached tasks that have not finished yet."""
    return len(_detached)


async def drain_detached(*, timeout: float | None = None) -> None:
    """Await currently detached tasks; used by tests and shutdown paths.

    Newly started detached tasks are not waited for.  ``timeout`` bounds the
    wait so callers cannot hang on a long-lived child.
    """
    pending = tuple(_detached)
    if not pending:
        return
    done, still_pending = await asyncio.wait(pending, timeout=timeout)
    for task in done:
        _log_failure(task)
    for task in still_pending:
        task.cancel()


def _discard_finished(task: asyncio.Task[Any]) -> None:
    _detached.discard(task)
    _log_failure(task)


def _log_failure(task: asyncio.Task[Any]) -> None:
    if task.cancelled():
        return
    exception = task.exception()
    if exception is not None:
        LOGGER.error("Detached background task failed: %r", exception, exc_info=exception)


__all__ = [
    "drain_detached",
    "pending_detached",
    "start_detached",
]
