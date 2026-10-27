"""S8 cancellation-contract tests.

Cancellation is the part of the migration that is easiest to get wrong: a broad
``except Exception`` silently swallows it, an unshielded ``finally`` never runs
its bounded cleanup, and a task group turns one child failure into an anonymous
``ExceptionGroup``.  These tests pin the contracts the production code relies on.
"""

from __future__ import annotations

import anyio
import pytest

from dojoagents.logging import get_logger

LOGGER = get_logger(__name__)


# ── parent cancellation ─────────────────────────────────────────────


@pytest.mark.anyio
async def test_parent_cancellation_propagates_and_runs_child_cleanup() -> None:
    cleaned: list[str] = []

    async def child() -> None:
        try:
            await anyio.sleep(30)
        finally:
            # The child is cancellation-pending here, so only a shielded
            # checkpoint may be awaited before the synchronous cleanup runs.
            with anyio.CancelScope(shield=True):
                await anyio.lowlevel.checkpoint()
            cleaned.append("child")

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(child)
        await anyio.sleep(0.02)
        task_group.cancel_scope.cancel()

    assert cleaned == ["child"]


@pytest.mark.anyio
async def test_cancellation_is_not_swallowed_by_except_exception() -> None:
    swallowed: list[str] = []

    async def job() -> None:
        try:
            await anyio.sleep(30)
        except Exception:  # must not catch the backend cancellation type
            swallowed.append("swallowed")

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(job)
        await anyio.sleep(0.02)
        task_group.cancel_scope.cancel()

    assert swallowed == []


@pytest.mark.anyio
async def test_cancellation_type_is_not_an_exception_subclass() -> None:
    assert not issubclass(anyio.get_cancelled_exc_class(), Exception)


# ── child failure ───────────────────────────────────────────────────


@pytest.mark.anyio
async def test_a_child_failure_cancels_siblings_and_surfaces_in_the_group() -> None:
    sibling_cancelled = False

    async def boom() -> None:
        await anyio.sleep(0.01)
        raise ValueError("child boom")

    async def sibling() -> None:
        nonlocal sibling_cancelled
        try:
            await anyio.sleep(30)
        except anyio.get_cancelled_exc_class():
            sibling_cancelled = True
            raise

    with pytest.raises(BaseExceptionGroup) as raised:
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(boom)
            task_group.start_soon(sibling)

    assert sibling_cancelled
    assert any(isinstance(exc, ValueError) for exc in raised.value.exceptions)


@pytest.mark.anyio
async def test_ordered_gather_keeps_a_single_task_failure_out_of_a_group() -> None:
    from dojoagents.utils.async_runtime import gather_ordered

    async def succeed(index: int) -> int:
        await anyio.sleep(0)
        return index

    async def fail() -> int:
        raise ValueError("only failure")

    results = await gather_ordered(
        [lambda: succeed(0), fail, lambda: succeed(2)],
        return_exceptions=True,
    )

    assert results[0] == 0
    assert isinstance(results[1], ValueError)
    assert results[2] == 2


# ── cleanup timeouts ────────────────────────────────────────────────


@pytest.mark.anyio
async def test_bounded_cleanup_abandons_a_slow_teardown_instead_of_hanging() -> None:
    finished = False

    with anyio.move_on_after(0.05) as scope:
        await anyio.sleep(30)  # models teardown that overruns its budget
        finished = True

    assert scope.cancelled_caught
    assert not finished


@pytest.mark.anyio
async def test_cleanup_that_exceeds_its_budget_still_lets_the_error_propagate() -> None:
    reached_handler = False

    with pytest.raises(ValueError, match="primary failure"):
        try:
            raise ValueError("primary failure")
        finally:
            with anyio.move_on_after(0.05):
                await anyio.sleep(30)
            reached_handler = True

    assert reached_handler


# ── repeated cancellation ───────────────────────────────────────────


@pytest.mark.anyio
async def test_repeated_cancellation_is_idempotent() -> None:
    reached_checkpoint_after = False

    with anyio.CancelScope() as scope:
        scope.cancel()
        scope.cancel()
        scope.cancel()
        await anyio.lowlevel.checkpoint()
        reached_checkpoint_after = True

    assert scope.cancel_called
    assert scope.cancelled_caught
    assert not reached_checkpoint_after


@pytest.mark.anyio
async def test_cancelling_a_finished_task_group_scope_is_harmless() -> None:
    async def quick() -> None:
        await anyio.sleep(0)

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(quick)

    # The scope belongs to a closed group; cancelling it must not raise.
    task_group.cancel_scope.cancel()
    await anyio.lowlevel.checkpoint()


# ── logging and persistence during cancellation ─────────────────────


@pytest.mark.anyio
async def test_cleanup_can_log_and_persist_while_cancellation_pending(tmp_path, caplog) -> None:
    record = tmp_path / "run.json"
    done: list[str] = []

    async def job() -> None:
        try:
            await anyio.sleep(30)
        finally:
            # Shielded, bounded cleanup is the only place an awaited write is
            # permitted once the task has started unwinding.
            with anyio.CancelScope(shield=True):
                LOGGER.warning("run cancelled; persisting final state")
                await anyio.to_thread.run_sync(record.write_text, '{"status": "cancelled"}')
            done.append("persisted")

    with caplog.at_level("WARNING"):
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(job)
            await anyio.sleep(0.02)
            task_group.cancel_scope.cancel()

    assert done == ["persisted"]
    assert record.read_text(encoding="utf-8") == '{"status": "cancelled"}'
    assert any("run cancelled" in message for message in caplog.messages)


@pytest.mark.anyio
async def test_ignoring_cancellation_without_shield_does_not_run_cleanup() -> None:
    """Documents the failure mode the shielded pattern above exists to avoid."""

    attempted: list[str] = []

    async def job() -> None:
        try:
            await anyio.sleep(30)
        finally:
            try:
                # No shield: this checkpoint raises immediately, so the
                # synchronous statement after it never executes.
                await anyio.lowlevel.checkpoint()
                attempted.append("cleanup")
            except anyio.get_cancelled_exc_class():
                pass

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(job)
        await anyio.sleep(0.02)
        task_group.cancel_scope.cancel()

    assert attempted == []
