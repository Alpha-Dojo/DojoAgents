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
