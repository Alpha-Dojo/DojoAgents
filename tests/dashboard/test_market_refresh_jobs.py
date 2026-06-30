import pytest
import asyncio
import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from dojoagents.dashboard.services.market_refresh_jobs import start_refresh_loop
from dojoagents.dashboard.services.constituent_kline_refresh_state import RefreshStateStore


@pytest.mark.asyncio
async def test_start_refresh_loop_triggers_preload_after_8am(tmp_path):
    # Setup mock registry and client
    mock_client = MagicMock()
    mock_client.preload_offline_data = AsyncMock()

    mock_registry = MagicMock()
    mock_registry.client = mock_client

    call_count = 0

    async def mock_sleep(seconds):
        nonlocal call_count
        call_count += 1
        if call_count >= 1:
            raise asyncio.CancelledError()

    # Mock datetime to 2026-06-29 08:30:00 (after 8 AM)
    with patch("dojoagents.dashboard.services.market_refresh_jobs.datetime") as mock_datetime:
        mock_datetime.datetime.now.return_value = datetime.datetime(2026, 6, 29, 8, 30)
        mock_datetime.time = datetime.time
        mock_datetime.timedelta = datetime.timedelta

        with patch("asyncio.sleep", side_effect=mock_sleep):
            await start_refresh_loop(runtime_dir=tmp_path, store_registry=mock_registry, poll_interval=1)

    # Verify preload was called and state was written for today (2026-06-29)
    mock_client.preload_offline_data.assert_called_once()

    refresh_store = RefreshStateStore(tmp_path)
    last_refresh = await refresh_store.get_last_refresh_date_async("preload_offline_data")
    assert last_refresh == datetime.date(2026, 6, 29)


@pytest.mark.asyncio
async def test_start_refresh_loop_triggers_preload_before_8am(tmp_path):
    mock_client = MagicMock()
    mock_client.preload_offline_data = AsyncMock()
    mock_registry = MagicMock()
    mock_registry.client = mock_client

    call_count = 0

    async def mock_sleep(seconds):
        nonlocal call_count
        call_count += 1
        if call_count >= 1:
            raise asyncio.CancelledError()

    # Mock datetime to 2026-06-29 07:30:00 (before 8 AM) -> target date is yesterday (2026-06-28)
    with patch("dojoagents.dashboard.services.market_refresh_jobs.datetime") as mock_datetime:
        mock_datetime.datetime.now.return_value = datetime.datetime(2026, 6, 29, 7, 30)
        mock_datetime.time = datetime.time
        mock_datetime.timedelta = datetime.timedelta

        with patch("asyncio.sleep", side_effect=mock_sleep):
            await start_refresh_loop(runtime_dir=tmp_path, store_registry=mock_registry, poll_interval=1)

    # Verify preload was called and state was written for yesterday (2026-06-28)
    mock_client.preload_offline_data.assert_called_once()

    refresh_store = RefreshStateStore(tmp_path)
    last_refresh = await refresh_store.get_last_refresh_date_async("preload_offline_data")
    assert last_refresh == datetime.date(2026, 6, 28)


@pytest.mark.asyncio
async def test_start_refresh_loop_skips_when_no_client(tmp_path):
    mock_registry = MagicMock()
    mock_registry.client = None

    call_count = 0

    async def mock_sleep(seconds):
        nonlocal call_count
        call_count += 1
        if call_count >= 1:
            raise asyncio.CancelledError()

    with patch("asyncio.sleep", side_effect=mock_sleep):
        await start_refresh_loop(runtime_dir=tmp_path, store_registry=mock_registry, poll_interval=1)

    refresh_store = RefreshStateStore(tmp_path)
    last_refresh = await refresh_store.get_last_refresh_date_async("preload_offline_data")
    assert last_refresh is None


@pytest.mark.asyncio
async def test_start_refresh_loop_skips_if_already_refreshed_today(tmp_path):
    refresh_store = RefreshStateStore(tmp_path)
    # Set last refresh to today (2026-06-29)
    await refresh_store.set_last_refresh_date_async("preload_offline_data", datetime.date(2026, 6, 29))

    mock_client = MagicMock()
    mock_client.preload_offline_data = AsyncMock()
    mock_registry = MagicMock()
    mock_registry.client = mock_client

    call_count = 0

    async def mock_sleep(seconds):
        nonlocal call_count
        call_count += 1
        if call_count >= 1:
            raise asyncio.CancelledError()

    # Mock datetime to 2026-06-29 10:00:00 (target date is today)
    with patch("dojoagents.dashboard.services.market_refresh_jobs.datetime") as mock_datetime:
        mock_datetime.datetime.now.return_value = datetime.datetime(2026, 6, 29, 10, 0)
        mock_datetime.time = datetime.time
        mock_datetime.timedelta = datetime.timedelta

        with patch("asyncio.sleep", side_effect=mock_sleep):
            await start_refresh_loop(runtime_dir=tmp_path, store_registry=mock_registry, poll_interval=1)

    # Should not call preload because it is already refreshed for the target date (today)
    mock_client.preload_offline_data.assert_not_called()


@pytest.mark.asyncio
async def test_start_refresh_loop_supports_sync_preload(tmp_path):
    # Setup mock registry and client with synchronous preload_offline_data method
    mock_client = MagicMock()
    mock_client.preload_offline_data = MagicMock()  # Synchronous!

    mock_registry = MagicMock()
    mock_registry.client = mock_client

    call_count = 0

    async def mock_sleep(seconds):
        nonlocal call_count
        call_count += 1
        if call_count >= 1:
            raise asyncio.CancelledError()

    # Mock datetime to 2026-06-29 08:30:00 (after 8 AM)
    with patch("dojoagents.dashboard.services.market_refresh_jobs.datetime") as mock_datetime:
        mock_datetime.datetime.now.return_value = datetime.datetime(2026, 6, 29, 8, 30)
        mock_datetime.time = datetime.time
        mock_datetime.timedelta = datetime.timedelta

        with patch("asyncio.sleep", side_effect=mock_sleep):
            await start_refresh_loop(runtime_dir=tmp_path, store_registry=mock_registry, poll_interval=1)

    # Verify preload was called and state was written for today (2026-06-29)
    mock_client.preload_offline_data.assert_called_once()

    refresh_store = RefreshStateStore(tmp_path)
    last_refresh = await refresh_store.get_last_refresh_date_async("preload_offline_data")
    assert last_refresh == datetime.date(2026, 6, 29)
