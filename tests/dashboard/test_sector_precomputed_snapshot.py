from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from dojoagents.dashboard.services.sector_precomputed_store import (
    SDK_PRECOMPUTED_PATHS,
    SectorPrecomputedStore,
)


@pytest.mark.asyncio
async def test_store_prefers_sdk_snapshot_small_tables(tmp_path) -> None:
    constituents = tmp_path / "constituents.parquet"
    sector_daily = tmp_path / "sector_daily.parquet"
    ticker_daily = tmp_path / "ticker_daily.parquet"
    pd.DataFrame(
        [
            {
                "market": "us",
                "ticker": "AAA",
                "level1_id": "1",
                "level2_id": "2",
                "level3_id": "3",
                "market_cap": 20_000_000_000.0,
            }
        ]
    ).to_parquet(constituents)
    pd.DataFrame(
        [
            {
                "market": "us",
                "scope": "L3",
                "level1_id": "1",
                "level2_id": "2",
                "level3_id": "3",
                "trade_date": "2026-09-29",
                "daily_return_pct": 1.0,
            }
        ]
    ).to_parquet(sector_daily)
    pd.DataFrame(
        [
            {
                "market": "us",
                "ticker": "AAA",
                "trade_date": "2026-09-29",
                "daily_return_pct": 1.0,
            }
        ]
    ).to_parquet(ticker_daily)

    snapshot = SimpleNamespace(
        backend="huggingface",
        repo_id="AlphaDojo/dojo_sector_precomputed",
        resolved_revision="revision-1",
        snapshot_token="token-1",
        files=(
            SimpleNamespace(relative_path="constituents.parquet", local_path=constituents),
            SimpleNamespace(relative_path="sector_daily.parquet", local_path=sector_daily),
            SimpleNamespace(relative_path="ticker_daily.parquet", local_path=ticker_daily),
        ),
    )

    class Client:
        async def ensure_offline_snapshots(self, *, paths):
            assert paths == list(SDK_PRECOMPUTED_PATHS)
            return [snapshot]

    store = SectorPrecomputedStore(tmp_path / "dashboard", snapshot_client=Client())
    await store.load()

    assert store.available() is True
    assert store.manifest()["source"] == "dojosdk_snapshot"
    assert store.manifest()["resolved_revision"] == "revision-1"
    assert store.get_sector_constituents_exact("1", "2", "3", market="us")[0]["ticker"] == "AAA"
    assert store.stats()["sector_daily_rows"] == 1
    assert store.stats()["ticker_daily_rows"] == 1
