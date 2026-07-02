from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from dojoagents.dashboard.services.dojo_data_gateway import GatewayResult
from dojoagents.dashboard.services.kline_bar_utils import (
    DATA_START_DATE,
    resolve_kline_limit_for_elapsed_days,
    resolve_tail_limit,
)
from dojoagents.dashboard.services.kline_store import KlineStore
from dojoagents.dashboard.services.stock_sector_store import StockSectorStore
from dojoagents.dashboard.services.stock_store import StockStore
from tests.dashboard.fakes.fake_dojo import FakeDojo


class KlineGateway:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows
        self.calls: list[dict] = []

    async def stock_klines(self, symbols, **window):
        self.calls.append(window)
        filtered = [row for row in self.rows if row["symbol"] in symbols]
        return GatewayResult(pd.DataFrame(filtered), None, "sdk_snapshot", False)


def _store(gateway) -> KlineStore:
    client = FakeDojo()
    return KlineStore(gateway, StockStore(client), StockSectorStore(client))


def test_resolve_tail_limit_uses_full_window_when_start_date_present() -> None:
    assert resolve_tail_limit(start_time=DATA_START_DATE, end_time="2026-07-01") == 0
    assert resolve_tail_limit(start_time=DATA_START_DATE, end_time="2026-07-01", limit=252) == 0
    assert resolve_tail_limit(limit=252) == 252


def test_resolve_kline_limit_for_elapsed_days_covers_2025_inception() -> None:
    limit = resolve_kline_limit_for_elapsed_days("2025-01-02", end_date="2026-07-01")
    assert 360 <= limit <= 500


@pytest.mark.asyncio
async def test_get_or_fetch_kline_keeps_full_window_from_data_start() -> None:
    rows = [
        {"symbol": "0700.HK", "bar_time": "2025-01-02", "close": 100.0},
        {"symbol": "0700.HK", "bar_time": "2025-06-20", "close": 110.0},
        {"symbol": "0700.HK", "bar_time": "2026-06-30", "close": 120.0},
    ]
    gateway = KlineGateway(rows)
    store = _store(gateway)

    result = await store.get_or_fetch_kline(
        "0700.HK",
        market="hk",
        start_time=DATA_START_DATE,
        end_time="2026-06-30",
    )

    assert result is not None
    assert [bar.bar_time for bar in result.bars] == [
        "2025-01-02",
        "2025-06-20",
        "2026-06-30",
    ]
    assert gateway.calls == [
        {
            "limit": resolve_kline_limit_for_elapsed_days(DATA_START_DATE, end_date="2026-06-30"),
            "start_time": DATA_START_DATE,
            "end_time": "2026-06-30",
        }
    ]
