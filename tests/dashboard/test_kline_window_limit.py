from __future__ import annotations

import pandas as pd
import pytest

from dojoagents.dashboard.services.dojo_data_gateway import GatewayResult
from dojoagents.dashboard.services.kline_bar_utils import (
    DATA_START_DATE,
    ashare_kline_symbol_candidates,
    infer_ashare_kline_suffix,
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


class TailOnlyKlineGateway:
    """Bulk index returns only the most recent ``tail`` bars unless a date window is requested."""

    def __init__(self, rows: list[dict], *, tail: int = 252) -> None:
        self.rows = rows
        self.tail = tail
        self.calls: list[dict] = []

    async def stock_klines(self, symbols, **window):
        self.calls.append(window)
        sym_rows = [row for row in self.rows if row["symbol"] in symbols]
        if window.get("start_time") or window.get("end_time"):
            start = str(window.get("start_time") or "")[:10]
            end = str(window.get("end_time") or "9999-99-99")[:10]
            filtered = [row for row in sym_rows if (not start or row["bar_time"][:10] >= start) and row["bar_time"][:10] <= end]
        else:
            filtered = sym_rows[-self.tail :]
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


def test_price_within_daily_range_is_inclusive() -> None:
    from dojoagents.dashboard.services.kline_bar_utils import price_within_daily_range

    assert price_within_daily_range(100.0, 100.0, 105.0)
    assert price_within_daily_range(105.0, 100.0, 105.0)
    assert not price_within_daily_range(99.99, 100.0, 105.0)


@pytest.mark.asyncio
async def test_get_or_fetch_kline_filters_single_day_with_iso_bar_time() -> None:
    rows = [
        {"symbol": "GOOG", "bar_time": "2026-06-17T00:00:00", "open": 170.0, "close": 171.0},
        {"symbol": "GOOG", "bar_time": "2026-06-18T00:00:00", "open": 176.0, "close": 177.0},
        {"symbol": "GOOG", "bar_time": "2026-06-19T00:00:00", "open": 178.0, "close": 179.0},
    ]
    gateway = KlineGateway(rows)
    store = _store(gateway)

    result = await store.get_or_fetch_kline(
        "GOOG",
        market="us",
        start_time="2026-06-18",
        end_time="2026-06-18",
    )

    assert result is not None
    assert len(result.bars) == 1
    assert result.bars[0].bar_time == "2026-06-18"
    assert result.bars[0].open == 176.0
    assert gateway.calls == [
        {
            "start_time": "2026-06-18",
            "end_time": "2026-06-18",
        }
    ]


@pytest.mark.asyncio
async def test_get_or_fetch_kline_historical_single_day_uses_date_window_on_gateway() -> None:
    rows = [
        {"symbol": "GOOGL", "bar_time": "2025-01-06", "open": 193.98, "close": 195.0},
        {"symbol": "GOOGL", "bar_time": "2026-06-18", "open": 176.0, "close": 177.0},
    ]
    gateway = TailOnlyKlineGateway(rows, tail=1)
    store = _store(gateway)

    result = await store.get_or_fetch_kline(
        "GOOGL",
        market="us",
        start_time="2025-01-06",
        end_time="2025-01-06",
    )

    assert result is not None
    assert len(result.bars) == 1
    assert result.bars[0].bar_time == "2025-01-06"
    assert result.bars[0].open == 193.98
    assert gateway.calls[0]["start_time"] == "2025-01-06"
    assert gateway.calls[0]["end_time"] == "2025-01-06"
    assert "limit" not in gateway.calls[0]


@pytest.mark.asyncio
async def test_single_day_omits_sdk_limit_so_late_bar_is_not_truncated() -> None:
    """Regression: limit=40 on a one-day window kept only 2025 bars and dropped 2026-07-03."""
    target = "2026-07-03"
    rows = [
        {"symbol": "0700.HK", "bar_time": "2025-01-02", "open": 400.0, "high": 410.0, "low": 395.0, "close": 405.0},
        {"symbol": "0700.HK", "bar_time": "2025-03-31", "open": 490.0, "high": 500.0, "low": 480.0, "close": 487.0},
        {
            "symbol": "0700.HK",
            "bar_time": f"{target}T00:00:00",
            "open": 433.0,
            "high": 445.8,
            "low": 431.2,
            "close": 431.2,
        },
    ]
    gateway = KlineGateway(rows)
    store = _store(gateway)

    result = await store.get_or_fetch_kline(
        "0700.HK",
        market="hk",
        start_time=target,
        end_time=target,
    )

    assert result is not None
    assert len(result.bars) == 1
    assert result.bars[0].bar_time == target
    assert result.bars[0].close == pytest.approx(431.2)
    assert gateway.calls == [{"start_time": target, "end_time": target}]


@pytest.mark.asyncio
async def test_get_or_fetch_kline_uses_min_bar_time_without_sdk_start_time() -> None:
    rows = [
        {"symbol": "GOOG", "bar_time": "2024-12-30", "close": 90.0},
        {"symbol": "GOOG", "bar_time": "2025-01-02", "close": 100.0},
        {"symbol": "GOOG", "bar_time": "2026-06-18", "close": 176.0},
    ]
    gateway = KlineGateway(rows)
    store = _store(gateway)

    result = await store.get_or_fetch_kline(
        "GOOG",
        market="us",
        min_bar_time=DATA_START_DATE,
    )

    assert result is not None
    assert [bar.bar_time for bar in result.bars] == ["2025-01-02", "2026-06-18"]
    assert gateway.calls == [{"limit": resolve_kline_limit_for_elapsed_days(DATA_START_DATE)}]


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
            "start_time": DATA_START_DATE,
            "end_time": "2026-06-30",
        }
    ]


def test_infer_ashare_kline_suffix_maps_exchange_codes() -> None:
    assert infer_ashare_kline_suffix("688008") == ".SS"
    assert infer_ashare_kline_suffix("600519") == ".SS"
    assert infer_ashare_kline_suffix("002230") == ".SZ"
    assert infer_ashare_kline_suffix("300750") == ".SZ"
    assert infer_ashare_kline_suffix("AAPL") is None
    assert infer_ashare_kline_suffix("688008.SS") is None


def test_ashare_kline_symbol_candidates_returns_suffixed_symbol() -> None:
    assert ashare_kline_symbol_candidates("688008") == ["688008.SS"]
    assert ashare_kline_symbol_candidates("002230") == ["002230.SZ"]
