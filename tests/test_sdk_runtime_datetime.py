from __future__ import annotations

import pytest

from dojoagents.harnesses.built_in.financial.tools.sdk_runtime import DojoSDKToolManager
from tests.dashboard.fakes.fake_dojo import FakeDojo


@pytest.mark.asyncio
async def test_benchmark_kline_tool_strips_timezone_without_shifting_date() -> None:
    client = FakeDojo(benchmark={"get_kline": {"data": []}})
    manager = DojoSDKToolManager()
    manager._client = client

    await manager._benchmark_kline(
        {
            "symbol": "000001.SS",
            "start_time": "2026-08-10T00:00:00+08:00",
            "end_time": "2026-08-12T23:59:59Z",
            "price_adj_date": "2026-08-12T00:00:00+08:00",
        }
    )

    assert client.benchmark.calls == [
        (
            "get_kline",
            {
                "symbol": "000001.SS",
                "kline_t": "1D",
                "start_time": "2026-08-10T00:00:00",
                "end_time": "2026-08-12T23:59:59",
                "price_adj_type": None,
                "price_adj_date": "2026-08-12T00:00:00",
                "limit": None,
            },
        )
    ]


@pytest.mark.asyncio
async def test_offline_stock_kline_tool_uses_snapshot_batch_and_keeps_metadata() -> None:
    client = FakeDojo(
        stocks={
            "get_klines": {
                "rows": [{"symbol": "AAPL", "kline_t": "1D", "bar_time": "2026-08-10"}],
                "snapshot": {
                    "backend": "huggingface",
                    "repo_id": "repo",
                    "resolved_revision": "revision",
                    "snapshot_token": "token",
                },
            }
        }
    )
    client._online = False
    manager = DojoSDKToolManager()
    manager._client = client

    result = await manager._stock_kline(
        {"symbol": "AAPL", "kline_t": "1d", "limit": 10}
    )

    assert result["data"]["total_num"] == 1
    assert result["data"]["snapshot"]["snapshot_token"] == "token"
    assert client.stocks.calls == [
        (
            "get_klines",
            {
                "symbols": ["AAPL"],
                "kline_t": "1D",
                "start": None,
                "end": None,
                "adjust": None,
                "adjustment_reference_date": None,
                "limit_per_symbol": 10,
            },
        )
    ]
