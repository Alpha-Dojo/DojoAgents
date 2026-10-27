"""Unit tests for the component-owned blocking portal (S7 / S8 unit category)."""

from __future__ import annotations

import threading
import time

import anyio
import pytest

from dojoagents.utils.blocking_portal import (
    DEFAULT_CALL_TIMEOUT_SECONDS,
    PortalCallTimeout,
    PortalClosedError,
    PortalThreadError,
    ThreadedBlockingPortal,
)


def _running_portal(name: str) -> ThreadedBlockingPortal:
    portal = ThreadedBlockingPortal(name=name)
    portal.start()
    return portal


def test_start_is_idempotent_and_keeps_one_loop_thread() -> None:
    portal = _running_portal("portal-idempotent-start")
    try:
        first = portal.loop_thread_ident
        portal.start()
        portal.start()
        assert portal.running
        assert portal.loop_thread_ident == first
        assert len([t for t in threading.enumerate() if t.ident == first]) == 1
    finally:
        portal.shutdown()


def test_shutdown_is_idempotent_and_joins_the_loop_thread() -> None:
    portal = _running_portal("portal-idempotent-stop")
    ident = portal.loop_thread_ident
    assert ident is not None

    portal.shutdown()
    portal.shutdown()

    assert portal.state == "closed"
    assert not portal.running
    assert [t for t in threading.enumerate() if t.ident == ident] == []


def test_call_runs_on_the_portal_loop_and_supports_arguments() -> None:
    portal = _running_portal("portal-call")
    try:
        assert portal.call(lambda: threading.get_ident()) == portal.loop_thread_ident
        assert portal.call(lambda left, *, right: left + right, 2, right=3) == 5
    finally:
        portal.shutdown()


def test_call_from_the_portal_loop_thread_is_refused() -> None:
    portal = _running_portal("portal-self-call")
    try:
        with pytest.raises(PortalThreadError):
            portal.call(lambda: portal.call(lambda: None))
    finally:
        portal.shutdown()


def test_concurrent_sync_calls_do_not_serialise_or_deadlock() -> None:
    portal = _running_portal("portal-concurrency")

    async def slow() -> str:
        await anyio.sleep(0.3)
        return "ok"

    results: dict[int, str] = {}

    def worker(index: int) -> None:
        results[index] = portal.call(slow)

    try:
        workers = [threading.Thread(target=worker, args=(index,)) for index in range(8)]
        started = time.monotonic()
        for thread in workers:
            thread.start()
        for thread in workers:
            thread.join()
        elapsed = time.monotonic() - started
    finally:
        portal.shutdown()

    assert len(results) == 8
    assert set(results.values()) == {"ok"}
    assert elapsed < 1.5, f"8 concurrent calls took {elapsed:.2f}s; they were serialised"


@pytest.mark.anyio
async def test_call_async_awaits_without_blocking_the_caller() -> None:
    portal = _running_portal("portal-call-async")
    try:
        assert await portal.call_async(lambda: "async-ok") == "async-ok"
        assert await portal.call_async(lambda left, *, right: left * right, 4, right=5) == 20
    finally:
        await portal.ashutdown()


def test_call_timeout_returns_promptly_and_cancels_the_coroutine() -> None:
    portal = _running_portal("portal-timeout")
    cancelled = threading.Event()

    async def hang() -> None:
        try:
            await anyio.sleep(30)
        except anyio.get_cancelled_exc_class():
            cancelled.set()
            raise

    try:
        started = time.monotonic()
        with pytest.raises(PortalCallTimeout):
            portal.call(hang, timeout=0.3)
        elapsed = time.monotonic() - started
        assert elapsed < 2.0, f"timeout path blocked for {elapsed:.2f}s"
        assert cancelled.wait(2.0), "the timed-out coroutine was never cancelled"
    finally:
        portal.shutdown()


@pytest.mark.anyio
async def test_call_async_timeout_is_bounded() -> None:
    portal = _running_portal("portal-timeout-async")

    async def hang() -> None:
        await anyio.sleep(30)

    try:
        started = time.monotonic()
        with pytest.raises(PortalCallTimeout):
            await portal.call_async(hang, timeout=0.3)
        assert time.monotonic() - started < 2.0
    finally:
        await portal.ashutdown()


def test_default_call_timeout_is_bounded() -> None:
    assert 0 < DEFAULT_CALL_TIMEOUT_SECONDS < float("inf")


def test_calls_after_shutdown_raise_an_explainable_error() -> None:
    portal = _running_portal("portal-late")
    portal.shutdown()

    with pytest.raises(PortalClosedError, match="not accepting calls"):
        portal.call(lambda: None)


def test_calls_before_start_raise_an_explainable_error() -> None:
    portal = ThreadedBlockingPortal(name="portal-never-started")

    with pytest.raises(PortalClosedError, match="state=new"):
        portal.call(lambda: None)


@pytest.mark.anyio
async def test_async_calls_after_shutdown_raise_an_explainable_error() -> None:
    portal = _running_portal("portal-late-async")
    await portal.ashutdown()

    with pytest.raises(PortalClosedError, match="not accepting calls"):
        await portal.call_async(lambda: None)


def test_shutdown_from_the_portal_thread_is_refused() -> None:
    portal = _running_portal("portal-self-shutdown")
    try:
        with pytest.raises(PortalThreadError):
            portal.call(portal.shutdown)
    finally:
        portal.shutdown()


def test_portal_can_be_restarted_after_shutdown_without_two_loops() -> None:
    portal = _running_portal("portal-restart")
    first = portal.loop_thread_ident
    portal.shutdown()
    assert [t for t in threading.enumerate() if t.ident == first] == []

    portal.start()
    try:
        assert portal.running
        assert portal.call(lambda: "restarted") == "restarted"
        # Exactly one loop thread exists, so the old loop was not left behind even
        # though the OS may hand the new thread the same ident.
        assert [t.name for t in threading.enumerate()].count("portal-restart") == 1
    finally:
        portal.shutdown()
