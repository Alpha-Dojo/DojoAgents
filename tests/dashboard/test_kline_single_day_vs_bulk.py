from __future__ import annotations

import pandas as pd
import pytest

from dojoagents.dashboard.services.dojo_data_gateway import DojoDataGateway
from dojoagents.dashboard.services.kline_bar_utils import DATA_START_DATE
from dojoagents.dashboard.services.kline_store import KlineStore
from dojoagents.dashboard.services.portfolio_kline_fetch import fetch_kline_bars_for_symbol
from tests.dashboard.fakes.fake_dojo import FakeDojo

TARGET = "2026-07-03"
SYMBOL = "0700.HK"


class BulkHasBarSingleDayEmptyFake(FakeDojo):
    """Reproduce production: bulk index has the bar; get_kline(single day) returns empty."""

    def __init__(self) -> None:
        super().__init__(
            stocks={
                "get_all_klines_with_df": pd.DataFrame(
                    [
                        {
                            "symbol": SYMBOL,
                            "bar_time": "2026-07-01",
                            "open": 420.0,
                            "high": 425.0,
                            "low": 418.0,
                            "close": 422.0,
                        },
                        {
                            "symbol": SYMBOL,
                            "bar_time": TARGET,
                            "open": 433.0,
                            "high": 445.8,
                            "low": 431.2,
                            "close": 431.2,
                        },
                    ]
                ),
                "get_kline": {"klines": []},
            }
        )


@pytest.mark.asyncio
async def test_gateway_single_day_uses_get_kline_and_can_return_empty_while_bulk_has_bar() -> None:
    client = BulkHasBarSingleDayEmptyFake()
    gateway = DojoDataGateway(client)

    bulk = await gateway.stock_klines([SYMBOL], limit=500)
    single = await gateway.stock_klines([SYMBOL], start_time=TARGET, end_time=TARGET)

    bulk_times = [str(v)[:10] for v in bulk.data["bar_time"].tolist()]
    assert TARGET in bulk_times
    assert single.data.empty
    assert client.stocks.calls[0][0] == "get_all_klines_with_df"
    single_call = client.stocks.calls[1]
    assert single_call[0] == "get_kline"
    assert single_call[1]["symbol"] == SYMBOL
    assert single_call[1]["start_time"] == TARGET
    assert single_call[1]["end_time"] == TARGET


@pytest.mark.asyncio
async def test_kline_store_single_day_returns_none_when_get_kline_empty() -> None:
    client = BulkHasBarSingleDayEmptyFake()
    gateway = DojoDataGateway(client)
    store = KlineStore(gateway, stock_store=object(), stock_sector_store=object())

    response = await store.get_or_fetch_kline(
        SYMBOL,
        market="hk",
        start_time=TARGET,
        end_time=TARGET,
    )

    assert response is None
    get_kline_call = next((call for call in client.stocks.calls if call[0] == "get_kline"), None)
    assert get_kline_call is not None
    assert "limit" not in get_kline_call[1]


@pytest.mark.asyncio
async def test_kline_store_single_day_returns_target_bar_when_sdk_has_full_window() -> None:
    rows = [
        {
            "symbol": SYMBOL,
            "bar_time": "2025-01-02T00:00:00",
            "open": 400.0,
            "high": 410.0,
            "low": 395.0,
            "close": 405.0,
        },
        {
            "symbol": SYMBOL,
            "bar_time": f"{TARGET}T00:00:00",
            "open": 433.0,
            "high": 445.8,
            "low": 431.2,
            "close": 431.2,
        },
    ]

    class RecordingGateway:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def stock_klines(self, symbols, **window):
            from dojoagents.dashboard.services.dojo_data_gateway import GatewayResult

            self.calls.append(window)
            filtered = [row for row in rows if row["symbol"] in symbols]
            return GatewayResult(pd.DataFrame(filtered), None, "sdk_snapshot", False)

    gateway = RecordingGateway()
    store = KlineStore(gateway, stock_store=object(), stock_sector_store=object())

    response = await store.get_or_fetch_kline(
        SYMBOL,
        market="hk",
        start_time=TARGET,
        end_time=TARGET,
    )

    assert response is not None
    assert len(response.bars) == 1
    assert response.bars[0].bar_time == TARGET
    assert gateway.calls == [{"start_time": TARGET, "end_time": TARGET}]


@pytest.mark.asyncio
async def test_kline_store_wide_min_bar_time_returns_target_bar() -> None:
    client = BulkHasBarSingleDayEmptyFake()
    gateway = DojoDataGateway(client)
    store = KlineStore(gateway, stock_store=object(), stock_sector_store=object())

    response = await store.get_or_fetch_kline(
        SYMBOL,
        market="hk",
        min_bar_time=DATA_START_DATE,
    )

    assert response is not None
    bar_times = [bar.bar_time[:10] for bar in response.bars]
    assert TARGET in bar_times


@pytest.mark.asyncio
async def test_portfolio_fetch_single_day_returns_target_bar() -> None:
    rows = [
        {
            "symbol": SYMBOL,
            "bar_time": "2025-01-02",
            "open": 400.0,
            "high": 410.0,
            "low": 395.0,
            "close": 405.0,
        },
        {
            "symbol": SYMBOL,
            "bar_time": TARGET,
            "open": 433.0,
            "high": 445.8,
            "low": 431.2,
            "close": 431.2,
        },
    ]

    class RecordingGateway:
        async def stock_klines(self, symbols, **window):
            from dojoagents.dashboard.services.dojo_data_gateway import GatewayResult

            filtered = [row for row in rows if row["symbol"] in symbols]
            return GatewayResult(pd.DataFrame(filtered), None, "sdk_snapshot", False)

    store = KlineStore(RecordingGateway(), stock_store=object(), stock_sector_store=object())

    bars = await fetch_kline_bars_for_symbol(
        store,
        symbol=SYMBOL,
        market="hk",
        order_time=TARGET,
        user_price=431.8,
    )

    assert len(bars) == 1
    assert bars[0].bar_time[:10] == TARGET
