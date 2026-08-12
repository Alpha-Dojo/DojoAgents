from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pandas as pd
import pytest
from dojo import ConflictError

from dojoagents.dashboard.cli.precompute_sector import _write_api_batches, upload_market_precomputed


@pytest.mark.asyncio
async def test_upload_market_precomputed_filters_market_and_normalizes_ids(tmp_path) -> None:
    frames = {
        "constituents.parquet": pd.DataFrame([{"market": "sh", "level1_id": "1", "level2_id": "2", "level3_id": "3", "ticker": "A", "role": "primary"}, {"market": "hk"}]),
        "ticker_daily.parquet": pd.DataFrame(
            [{"market": "sh", "ticker": "OLD", "trade_date": "2026-08-11"}, {"market": "sh", "ticker": "A", "trade_date": "2026-08-12"}, {"market": "hk"}]
        ),
        "sector_daily.parquet": pd.DataFrame(
            [
                {"market": "sh", "scope": "L1", "level1_id": "1", "level2_id": "", "level3_id": "", "trade_date": "2026-08-11"},
                {"market": "sh", "scope": "L1", "level1_id": "1", "level2_id": "", "level3_id": "", "trade_date": "2026-08-12"},
                {"market": "hk"},
            ]
        ),
    }
    client = MagicMock()
    client.sectors.create_constituents = AsyncMock()
    client.sectors.create_ticker_daily = AsyncMock()
    client.sectors.create_daily = AsyncMock()

    with patch("dojoagents.dashboard.cli.precompute_sector.pd.read_parquet", side_effect=lambda path: frames[path.name]):
        counts = await upload_market_precomputed(client, tmp_path, "cn", start_date="2026-08-12")

    assert counts == {"constituents.parquet": 1, "ticker_daily.parquet": 1, "sector_daily.parquet": 1}
    constituent = client.sectors.create_constituents.await_args.kwargs["observations"][0]
    sector_daily = client.sectors.create_daily.await_args.kwargs["observations"][0]
    assert (constituent["level1_id"], constituent["level2_id"], constituent["level3_id"]) == (1, 2, 3)
    assert constituent["market"] == "cn"
    assert (sector_daily["level1_id"], sector_daily["level2_id"], sector_daily["level3_id"]) == (1, 0, 0)


@pytest.mark.asyncio
async def test_write_api_batches_replaces_conflicting_batch() -> None:
    request = httpx.Request("POST", "https://api.example.test")
    response = httpx.Response(409, request=request)
    method = AsyncMock(side_effect=[ConflictError("conflict", response=response, body={}), MagicMock()])
    client = MagicMock()
    client.sectors.create_daily = method

    await _write_api_batches(client, "create_daily", [{"market": "cn"}])

    assert method.await_count == 2
    assert method.await_args_list[0].kwargs == {"observations": [{"market": "cn"}]}
    assert method.await_args_list[1].kwargs == {"observations": [{"market": "cn"}], "replace": True}
