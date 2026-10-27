from __future__ import annotations

import asyncio
import threading

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from dojo.client.async_client import AsyncDojo
from dojo.datasource.config import HFConfig
from dojo.datasource.huggingface import HuggingFaceDataSource, HuggingFaceKlineDataSource
from dojo.datasource.registry import HF_REGISTRY
from dojo.types.snapshot import SnapshotFile, SnapshotRef


pytestmark = pytest.mark.offline_integration


def _config(tmp_path, *, retries: int = 2) -> HFConfig:
    return HFConfig(
        backend="huggingface",
        cache_dir=str(tmp_path),
        local_only=True,
        download_timeout_seconds=7,
        etag_timeout_seconds=3,
        max_download_retries=retries,
    )


def test_offline_stock_kline_registry_filters_and_orders_by_bar_time() -> None:
    spec = HF_REGISTRY["/api/qdata/v1/stock/kline"]
    assert spec.time_field == "bar_time"
    assert spec.order_desc is True


def test_offline_kline_filters_datetime_window_and_returns_recent_limit(
    tmp_path,
    monkeypatch,
) -> None:
    parquet_path = tmp_path / "data.parquet"
    pq.write_table(
        pa.Table.from_pandas(
            pd.DataFrame(
                [
                    {"symbol": "AAA", "kline_t": "1D", "bar_time": pd.Timestamp("2026-01-01"), "close": 1.0},
                    {"symbol": "AAA", "kline_t": "1D", "bar_time": pd.Timestamp("2026-01-02"), "close": 2.0},
                    {"symbol": "AAA", "kline_t": "1D", "bar_time": pd.Timestamp("2026-01-03"), "close": 3.0},
                ]
            ),
            preserve_index=False,
        ),
        parquet_path,
    )
    snapshot = SnapshotRef(
        backend="huggingface",
        repo_id="AlphaDojo/dojo_stock_kline",
        resolved_revision="test",
        snapshot_token="test-token",
        files=(
            SnapshotFile(
                relative_path="data.parquet",
                local_path=parquet_path,
                size=parquet_path.stat().st_size,
            ),
        ),
    )
    source = HuggingFaceKlineDataSource(_config(tmp_path))
    monkeypatch.setattr(
        source._snapshot_resolver,
        "ensure_offline_snapshots",
        lambda **_kwargs: [snapshot],
    )

    result = source.fetch(
        method="GET",
        path="/api/qdata/v1/stock/kline",
        params={
            "symbol": "AAA",
            "start_time": "2026-01-01",
            "end_time": "2026-01-03",
            "limit": 2,
        },
    )

    # The per-symbol limit selects the latest two rows, then the public result
    # is normalized back to chronological order.
    assert [row["close"] for row in result["data"]["data"]] == [2.0, 3.0]


def test_huggingface_datasource_does_not_start_download_watchdog(tmp_path) -> None:
    before = {thread.ident for thread in threading.enumerate()}
    HuggingFaceDataSource(_config(tmp_path))
    started = [
        thread.name
        for thread in threading.enumerate()
        if thread.ident not in before and thread.name == "DojoSDK-DownloadWatchdog"
    ]
    assert started == []


@pytest.mark.asyncio
async def test_async_dojo_cancellation_reaches_offline_preload_worker() -> None:
    entered = threading.Event()
    cancelled = threading.Event()

    class DataSource:
        def preload(self, _paths):
            entered.set()
            assert cancelled.wait(timeout=2)

        def cancel_preload(self):
            cancelled.set()

    client = object.__new__(AsyncDojo)
    client._data_source = DataSource()
    task = asyncio.create_task(client.preload_offline_data(["/blocked"]))
    assert await asyncio.to_thread(entered.wait, 1)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cancelled.is_set()


@pytest.mark.asyncio
async def test_async_dojo_applies_client_limits_to_offline_downloads(monkeypatch) -> None:
    monkeypatch.setenv("DOJO_ONLINE", "0")
    monkeypatch.delenv("DOJO_HF_DOWNLOAD_TIMEOUT", raising=False)
    monkeypatch.delenv("DOJO_HF_MAX_RETRIES", raising=False)

    client = AsyncDojo(timeout=17, max_retries=4)
    try:
        assert client._data_source._cfg.download_timeout_seconds == 17
        assert client._data_source._cfg.max_download_retries == 4
    finally:
        await client._client.aclose()
