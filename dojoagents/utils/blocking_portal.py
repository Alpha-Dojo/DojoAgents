"""Component-owned blocking portals that bridge sync threads and an event loop.

AnyIO has no primitive that lets an *async* caller await work running on a
*foreign* event loop without occupying a thread — the bridge **is** a thread, by
construction.  ``anyio.from_thread.start_blocking_portal`` is therefore the only
supported way for a component to own a dedicated loop that synchronous code can
also drive (CLI startup, signal handlers, plugin registration).

This module wraps that context manager in an explicit, idempotent lifecycle so
the rules in the S7 migration brief cannot be broken by accident::

    start -> ready -> accept sync-thread calls -> stop accepting -> close -> join

Invariants enforced here:

* exactly one portal per component; ``start`` and ``shutdown`` are idempotent and
  never leave two event loops alive at the same time;
* ``call``/``call_async`` refuse to run on the portal's own loop thread, which
  would deadlock the portal against itself;
* a call submitted before ``start`` or after ``shutdown`` began raises
  :class:`PortalClosedError` instead of hanging or silently degrading;
* shutdown is explicit — there is no ``__del__`` and no reliance on the garbage
  collector to run asynchronous cleanup;
* the hand-rolled ``new_event_loop()`` + ``run_forever`` thread and every
  ``run_coroutine_threadsafe``/``wrap_future`` bridge are replaced outright, so a
  component never keeps both the old loop and the new portal alive.
"""

from __future__ import annotations

import concurrent.futures
import threading
from collections.abc import Callable
from functools import partial
from typing import Any, TypeVar, cast

import anyio
from anyio.from_thread import BlockingPortal, start_blocking_portal

from dojoagents.logging import get_logger
from dojoagents.utils.async_runtime import run_sync_bounded

LOGGER = get_logger(__name__)

T = TypeVar("T")

DEFAULT_CALL_TIMEOUT_SECONDS = 120.0
DEFAULT_SHUTDOWN_TIMEOUT_SECONDS = 10.0
DEFAULT_BRIDGE_CONCURRENCY = 8

_STATE_NEW = "new"
_STATE_RUNNING = "running"
_STATE_CLOSING = "closing"
_STATE_CLOSED = "closed"


class PortalError(RuntimeError):
    """Base class for portal lifecycle failures."""


class PortalClosedError(PortalError):
    """A portal was used before ``start`` or after ``shutdown`` began."""


class PortalThreadError(PortalError):
    """A portal was used from its own event-loop thread (a guaranteed deadlock)."""


class PortalCallTimeout(PortalError, TimeoutError):
    """A synchronous portal call exceeded its declared deadline."""


def _cancel_in_background(future: concurrent.futures.Future[Any], *, name: str) -> None:
    """Cancel ``future`` off the calling thread.

    ``concurrent.futures.Future.cancel()`` runs its done callbacks inline, and the
    portal's callback has to hand the cancellation back to the portal loop.  Doing
    that on a caller that has just given up on the deadline would re-block it for
    as long as the loop stays busy, which is exactly what the timeout was meant to
    avoid.
    """

    def _cancel() -> None:
        try:
            future.cancel()
        except Exception:  # noqa: BLE001 - best-effort cleanup
            LOGGER.debug("portal background cancel failed for %s", name, exc_info=True)

    threading.Thread(target=_cancel, name=name, daemon=True).start()


class ThreadedBlockingPortal:
    """A component-owned event loop thread with an explicit lifecycle.

    The portal is deliberately *not* a global: whoever constructs it owns it and
    is responsible for calling :meth:`shutdown`, which stops accepting calls,
    closes the portal, and joins the loop thread.
    """

    def __init__(
        self,
        *,
        name: str,
        backend: str = "asyncio",
        bridge_concurrency: int = DEFAULT_BRIDGE_CONCURRENCY,
    ) -> None:
        if bridge_concurrency <= 0:
            raise ValueError("bridge_concurrency must be greater than zero")
        self.name = name
        self._backend = backend
        self._bridge_concurrency = bridge_concurrency
        self._guard = threading.Lock()
        self._state = _STATE_NEW
        self._portal: BlockingPortal | None = None
        self._portal_cm: Any | None = None
        self._loop_thread_ident: int | None = None
        self._bridge_limiter: anyio.CapacityLimiter | None = None

    # ── introspection ───────────────────────────────────────────────

    @property
    def state(self) -> str:
        with self._guard:
            return self._state

    @property
    def running(self) -> bool:
        with self._guard:
            return self._state == _STATE_RUNNING

    @property
    def loop_thread_ident(self) -> int | None:
        return self._loop_thread_ident

    # ── lifecycle ───────────────────────────────────────────────────

    def start(self) -> None:
        """Create the portal loop thread and block until it is ready.

        Idempotent: a running portal is returned unchanged, and a previously
        shut down portal is recreated from scratch (never two at once).
        """

        with self._guard:
            if self._state == _STATE_RUNNING:
                return
            self._start_locked()

    def _start_locked(self) -> None:
        portal_cm = start_blocking_portal(self._backend, name=self.name)
        portal = portal_cm.__enter__()
        try:
            # Reading the thread identity from inside the portal loop keeps this
            # module free of AnyIO private attributes.
            loop_thread_ident = portal.call(threading.get_ident)
        except BaseException:
            portal_cm.__exit__(None, None, None)
            raise
        self._portal_cm = portal_cm
        self._portal = portal
        self._loop_thread_ident = loop_thread_ident
        self._bridge_limiter = None
        self._state = _STATE_RUNNING

    def shutdown(self, *, timeout: float = DEFAULT_SHUTDOWN_TIMEOUT_SECONDS) -> None:
        """Stop accepting calls, close the portal, and wait for its thread to exit.

        Idempotent.  ``timeout`` bounds how long the close is allowed to take
        before the caller gives up waiting; the loop thread is a daemon and still
        exits on its own once the remaining tasks unwind.
        """

        if threading.get_ident() == self._loop_thread_ident:
            raise PortalThreadError(f"portal '{self.name}' cannot be shut down from its own event-loop thread")
        with self._guard:
            portal_cm = self._portal_cm
            portal = self._portal
            if portal_cm is None or portal is None:
                self._state = _STATE_CLOSED
                return
            # Stop accepting new calls *before* touching the loop so late callers
            # always get an explainable error rather than a hang.
            self._state = _STATE_CLOSING
            self._portal = None
            self._portal_cm = None
            self._loop_thread_ident = None
            self._bridge_limiter = None
        try:
            # Cancel whatever is still running so the loop can wind down.
            portal.call(portal.stop, True)
        except RuntimeError:
            pass
        except Exception:  # noqa: BLE001 - shutdown must not fail on a dead loop
            LOGGER.debug("portal '%s': stop() raised during shutdown", self.name, exc_info=True)
        self._close_portal(portal_cm, timeout=timeout)
        with self._guard:
            self._state = _STATE_CLOSED

    def _close_portal(self, portal_cm: Any, *, timeout: float) -> None:
        finished = threading.Event()
        failure: list[BaseException] = []

        def _close() -> None:
            try:
                portal_cm.__exit__(None, None, None)
            except BaseException as exc:  # noqa: BLE001 - report, never raise from a closer thread
                failure.append(exc)
            finally:
                finished.set()

        closer = threading.Thread(target=_close, name=f"{self.name}:close", daemon=True)
        closer.start()
        if not finished.wait(timeout):
            LOGGER.warning(
                "portal '%s' did not finish closing within %ss; its loop thread will exit once the remaining tasks unwind",
                self.name,
                timeout,
            )
            return
        closer.join()
        if failure:
            LOGGER.warning("portal '%s' raised while closing: %r", self.name, failure[0])

    async def ashutdown(self, *, timeout: float = DEFAULT_SHUTDOWN_TIMEOUT_SECONDS) -> None:
        """Async-safe :meth:`shutdown` that never blocks the calling event loop."""

        if self.state == _STATE_CLOSED:
            return
        await self.run_sync(
            self.shutdown,
            timeout=timeout,
            abandon_on_cancel=True,
        )

    # ── synchronous-thread calls ────────────────────────────────────

    def call(
        self,
        func: Callable[..., T],
        *args: Any,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> T:
        """Run ``func`` on the portal loop and return its result.

        Must be called from a thread other than the portal's own loop thread.
        """

        portal = self._active_portal()
        target: Callable[..., Any] = partial(func, **kwargs) if kwargs else func
        future = portal.start_task_soon(target, *args)
        try:
            return cast(T, future.result(timeout=timeout))
        except concurrent.futures.TimeoutError as exc:
            # Cancelling the future cancels the coroutine it is driving, but the
            # cancellation handshake blocks until the portal loop can service it,
            # so it must not run on the timing-out caller's thread.
            _cancel_in_background(future, name=f"{self.name}:cancel")
            raise PortalCallTimeout(f"portal '{self.name}' call timed out after {timeout:g}s") from exc

    def start_task(
        self,
        func: Callable[..., Any],
        *args: Any,
        name: str | None = None,
    ) -> concurrent.futures.Future[Any]:
        """Schedule ``func`` on the portal loop without waiting for it."""

        return self._active_portal().start_task_soon(func, *args, name=name)

    # ── asynchronous calls ──────────────────────────────────────────

    async def run_sync(
        self,
        function: Callable[..., T],
        /,
        *args: Any,
        abandon_on_cancel: bool = False,
        **kwargs: Any,
    ) -> T:
        """Run blocking bridge work through this portal's private limiter.

        This is the bounded path for synchronous lifecycle operations associated
        with the portal, such as cancelling a cross-loop future or waiting for a
        component to settle. It deliberately does not consume the project's
        file-I/O or SDK-I/O worker budgets.
        """

        return await run_sync_bounded(
            function,
            *args,
            limiter=self._bridge_limiter_for(),
            abandon_on_cancel=abandon_on_cancel,
            **kwargs,
        )

    async def call_async(
        self,
        func: Callable[..., T],
        *args: Any,
        timeout: float | None = DEFAULT_CALL_TIMEOUT_SECONDS,
        **kwargs: Any,
    ) -> T:
        """Run ``func`` on the portal loop, awaiting the result without blocking.

        A worker thread is consumed for the duration of the call because AnyIO
        has no thread-free way to await a foreign loop; the wait is always
        bounded and uses a portal-private limiter so MCP/agent bridges cannot
        starve the project's file/SDK worker pools.
        """

        self._active_portal()
        effective_timeout = DEFAULT_CALL_TIMEOUT_SECONDS if timeout is None else timeout
        return await self.run_sync(
            self.call,
            func,
            *args,
            timeout=effective_timeout,
            abandon_on_cancel=True,
            **kwargs,
        )

    def _bridge_limiter_for(self) -> anyio.CapacityLimiter:
        limiter = self._bridge_limiter
        if limiter is None:
            limiter = anyio.CapacityLimiter(self._bridge_concurrency)
            self._bridge_limiter = limiter
        return limiter

    # ── guards ──────────────────────────────────────────────────────

    def _active_portal(self) -> BlockingPortal:
        if self._loop_thread_ident is not None and threading.get_ident() == self._loop_thread_ident:
            raise PortalThreadError(
                f"portal '{self.name}' cannot be used from its own event-loop thread; "
                "call the coroutine directly instead of re-entering the portal"
            )
        with self._guard:
            state = self._state
            portal = self._portal
        if state != _STATE_RUNNING or portal is None:
            raise PortalClosedError(f"portal '{self.name}' is not accepting calls (state={state})")
        return portal


__all__ = [
    "DEFAULT_BRIDGE_CONCURRENCY",
    "DEFAULT_CALL_TIMEOUT_SECONDS",
    "DEFAULT_SHUTDOWN_TIMEOUT_SECONDS",
    "PortalCallTimeout",
    "PortalClosedError",
    "PortalError",
    "PortalThreadError",
    "ThreadedBlockingPortal",
]
