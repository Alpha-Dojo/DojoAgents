from __future__ import annotations

import asyncio
import contextlib
import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dojoagents.dashboard.services.constituent_kline_refresh_state import RefreshStateStore
from dojoagents.dashboard.services.market_refresh_jobs import start_refresh_loop


KLINE_PATH = "/api/qdata/v1/stock/kline"
KLINE_REPO = "AlphaDojo/dojo_stock_kline"


def _sync_result(
    *,
    changed: bool = True,
    updated_repos: tuple[str, ...] = (KLINE_REPO,),
    failures: tuple[object, ...] = (),
) -> SimpleNamespace:
    return SimpleNamespace(
        changed=changed,
        updated_repos=updated_repos,
        failures=failures,
    )


async def _cancel_after_first_sleep(_seconds: float) -> None:
    raise asyncio.CancelledError()


async def _run_one_iteration(
    tmp_path,
    registry,
    *,
    now: datetime.datetime,
    hot_paths: list[str] | None = None,
) -> None:
    with patch("dojoagents.dashboard.services.market_refresh_jobs.datetime") as mock_datetime:
        mock_datetime.datetime.now.return_value = now
        mock_datetime.time = datetime.time
        mock_datetime.timedelta = datetime.timedelta
        with patch(
            "dojoagents.dashboard.services.market_refresh_jobs.anyio.sleep",
            side_effect=_cancel_after_first_sleep,
        ):
            with contextlib.suppress(asyncio.CancelledError):
                await start_refresh_loop(
                    runtime_dir=tmp_path,
                    store_registry=registry,
                    poll_interval=1,
                    paths=[KLINE_PATH],
                    hot_paths=hot_paths or [],
                )


@pytest.mark.asyncio
async def test_start_refresh_loop_syncs_explicit_paths_after_8am(tmp_path):
    client = MagicMock()
    client.sync_offline_snapshots = AsyncMock(return_value=_sync_result())
    registry = MagicMock()
    registry.client = client
    registry.refresh_after_offline_data_update = AsyncMock()

    await _run_one_iteration(
        tmp_path,
        registry,
        now=datetime.datetime(2026, 6, 29, 8, 30),
    )

    client.sync_offline_snapshots.assert_awaited_once_with(
        paths=[KLINE_PATH],
        repos=None,
        check_remote=True,
        force=False,
    )
    registry.refresh_after_offline_data_update.assert_awaited_once_with(
        updated_repos=(KLINE_REPO,),
    )
    refresh_store = RefreshStateStore(tmp_path)
    assert await refresh_store.get_last_refresh_date_async("offline_snapshots") == datetime.date(2026, 6, 29)


@pytest.mark.asyncio
async def test_start_refresh_loop_uses_previous_date_before_8am(tmp_path):
    client = MagicMock()
    client.sync_offline_snapshots = AsyncMock(return_value=_sync_result(changed=False, updated_repos=()))
    registry = MagicMock()
    registry.client = client
    registry.refresh_after_offline_data_update = AsyncMock()

    await _run_one_iteration(
        tmp_path,
        registry,
        now=datetime.datetime(2026, 6, 29, 7, 30),
    )

    client.sync_offline_snapshots.assert_awaited_once()
    registry.refresh_after_offline_data_update.assert_not_awaited()
    refresh_store = RefreshStateStore(tmp_path)
    assert await refresh_store.get_last_refresh_date_async("offline_snapshots") == datetime.date(2026, 6, 28)


@pytest.mark.asyncio
async def test_start_refresh_loop_skips_when_no_client(tmp_path):
    registry = MagicMock()
    registry.client = None

    await _run_one_iteration(
        tmp_path,
        registry,
        now=datetime.datetime(2026, 6, 29, 8, 30),
    )

    refresh_store = RefreshStateStore(tmp_path)
    assert await refresh_store.get_last_refresh_date_async("offline_snapshots") is None


@pytest.mark.asyncio
async def test_start_refresh_loop_skips_if_already_refreshed_today(tmp_path):
    refresh_store = RefreshStateStore(tmp_path)
    await refresh_store.set_last_refresh_date_async("offline_snapshots", datetime.date(2026, 6, 29))
    client = MagicMock()
    client.sync_offline_snapshots = AsyncMock(return_value=_sync_result())
    registry = MagicMock()
    registry.client = client

    await _run_one_iteration(
        tmp_path,
        registry,
        now=datetime.datetime(2026, 6, 29, 10, 0),
    )

    client.sync_offline_snapshots.assert_not_awaited()


@pytest.mark.asyncio
async def test_start_refresh_loop_checks_hot_snapshot_after_daily_sync(tmp_path):
    hot_path = "/api/qdata/v1/stocks/current_quote"
    refresh_store = RefreshStateStore(tmp_path)
    await refresh_store.set_last_refresh_date_async("offline_snapshots", datetime.date(2026, 6, 29))
    client = MagicMock()
    client.sync_offline_snapshots = AsyncMock(
        return_value=_sync_result(
            updated_repos=("AlphaDojo/dojo_quote",),
        )
    )
    registry = MagicMock()
    registry.client = client
    registry.refresh_after_offline_data_update = AsyncMock()

    with patch("dojoagents.dashboard.services.market_refresh_jobs.datetime") as mock_datetime:
        mock_datetime.datetime.now.return_value = datetime.datetime(2026, 6, 29, 10, 0)
        mock_datetime.time = datetime.time
        mock_datetime.timedelta = datetime.timedelta
        with patch(
            "dojoagents.dashboard.services.market_refresh_jobs.anyio.sleep",
            side_effect=_cancel_after_first_sleep,
        ):
                with contextlib.suppress(asyncio.CancelledError):
                    await start_refresh_loop(
                        runtime_dir=tmp_path,
                        registry=registry,
                        poll_interval=1,
                        paths=[KLINE_PATH, hot_path],
                        hot_paths=[hot_path],
                    )

    client.sync_offline_snapshots.assert_awaited_once_with(
        paths=[hot_path],
        repos=None,
        check_remote=True,
        force=False,
    )
    registry.refresh_after_offline_data_update.assert_awaited_once_with(
        updated_repos=("AlphaDojo/dojo_quote",),
    )


@pytest.mark.asyncio
async def test_start_refresh_loop_supports_sync_snapshot_client(tmp_path):
    client = MagicMock()
    client.sync_offline_snapshots = MagicMock(return_value=_sync_result())
    registry = MagicMock()
    registry.client = client
    registry.refresh_after_offline_data_update = AsyncMock()

    await _run_one_iteration(
        tmp_path,
        registry,
        now=datetime.datetime(2026, 6, 29, 8, 30),
    )

    client.sync_offline_snapshots.assert_called_once_with(
        paths=[KLINE_PATH],
        repos=None,
        check_remote=True,
        force=False,
    )


@pytest.mark.asyncio
async def test_failed_repo_does_not_invalidate_or_mark_refresh_complete(tmp_path):
    client = MagicMock()
    client.sync_offline_snapshots = AsyncMock(
        return_value=_sync_result(
            changed=False,
            updated_repos=(),
            failures=(SimpleNamespace(repo_id=KLINE_REPO),),
        )
    )
    registry = MagicMock()
    registry.client = client
    registry.refresh_after_offline_data_update = AsyncMock()

    await _run_one_iteration(
        tmp_path,
        registry,
        now=datetime.datetime(2026, 6, 29, 8, 30),
    )

    registry.refresh_after_offline_data_update.assert_not_awaited()
    refresh_store = RefreshStateStore(tmp_path)
    assert await refresh_store.get_last_refresh_date_async("offline_snapshots") is None


@pytest.mark.asyncio
async def test_partial_sync_invalidates_only_successfully_committed_repo(tmp_path):
    failed_repo = "AlphaDojo/dojo_sector_info"
    client = MagicMock()
    client.sync_offline_snapshots = AsyncMock(
        return_value=_sync_result(
            changed=True,
            updated_repos=(KLINE_REPO,),
            failures=(SimpleNamespace(repo_id=failed_repo),),
        )
    )
    registry = MagicMock()
    registry.client = client
    registry.refresh_after_offline_data_update = AsyncMock()

    await _run_one_iteration(
        tmp_path,
        registry,
        now=datetime.datetime(2026, 6, 29, 8, 30),
    )

    registry.refresh_after_offline_data_update.assert_awaited_once_with(
        updated_repos=(KLINE_REPO,),
    )
    refresh_store = RefreshStateStore(tmp_path)
    assert await refresh_store.get_last_refresh_date_async("offline_snapshots") is None


def test_start_refresh_loop_requires_explicit_snapshot_scope(tmp_path):
    registry = MagicMock()
    registry.client = MagicMock()

    with pytest.raises(ValueError, match="explicit paths or repos"):
        asyncio.run(start_refresh_loop(runtime_dir=tmp_path, registry=registry))
