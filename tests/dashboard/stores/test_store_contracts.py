from __future__ import annotations

import inspect

import pytest

import dojoagents.dashboard.services.kline_store as kline_store_module
from dojoagents.dashboard.schemas.portfolio import CreatePortfolioRequest, PortfolioDetail
from dojoagents.dashboard.schemas.stock_kline import ConstituentKlineBatchResponse
from dojoagents.dashboard.schemas.stock import Stock, StockQuote
from dojoagents.dashboard.schemas.stock_sector import StockSectorLabel
from dojoagents.dashboard.services.kline_store import KlineStore
from dojoagents.dashboard.services.portfolio_allocation import initial_shares_for_new_holding
from dojoagents.dashboard.services.portfolio_service import PortfolioService
from dojoagents.dashboard.services.portfolio_store import PortfolioStore
from dojoagents.dashboard.services.sector_store import ResolvedSectorPath
from dojoagents.dashboard.services.stock_sector_store import StockSectorStore
from dojoagents.dashboard.services.stock_store import StockStore
from tests.dashboard.fakes.fake_dojo import FakeDojo


def _sector_path() -> ResolvedSectorPath:
    return ResolvedSectorPath(
        level1_id="1",
        level2_id="2",
        level3_id="3",
        level1_zh="科技",
        level1_en="Technology",
        level2_zh="软件",
        level2_en="Software",
        level3_zh="应用软件",
        level3_en="Application Software",
    )


def _quoted_stock(ticker: str = "AAPL", market: str = "us") -> Stock:
    return Stock(
        ticker=ticker,
        market=market,
        short_name=ticker,
        stock_quote=StockQuote(
            ticker=ticker,
            name=ticker,
            last_price=100.0,
            pre_close=99.0,
            open=99.0,
            high=101.0,
            low=98.0,
            change=1.0,
            change_percent=1.0,
            volume=100,
            amount=10_000.0,
            avg_price=100.0,
            market_cap=1_000_000.0,
            turn_rate=1.0,
            pe=20.0,
            pb=3.0,
        ),
    )


def test_in_memory_stock_and_sector_getters_are_synchronous() -> None:
    client = FakeDojo()
    stocks = StockStore(client)
    sectors = StockSectorStore(client)
    stock = _quoted_stock()
    label = StockSectorLabel(ticker="AAPL", market="us")
    stocks.by_ticker["us:AAPL"] = stock
    sectors._cache["us"]["AAPL"] = label

    assert not inspect.iscoroutinefunction(stocks.get)
    assert not inspect.iscoroutinefunction(sectors.get)
    assert stocks.get("us", "AAPL") is stock
    assert sectors.get("us", "AAPL") is label
    assert inspect.iscoroutinefunction(stocks.load)
    assert inspect.iscoroutinefunction(sectors.load)


@pytest.mark.asyncio
async def test_kline_get_or_fetch_and_load_all_share_memory_cache() -> None:
    import pandas as pd

    client = FakeDojo(
        stocks={
            "get_all_klines_with_df": pd.DataFrame(
                [
                    {
                        "symbol": "AAPL",
                        "bar_time": "2026-06-20",
                        "open": 99,
                        "high": 101,
                        "low": 98,
                        "close": 100,
                    }
                ]
            )
        }
    )
    store = KlineStore(client, StockStore(client), StockSectorStore(client))

    response = await store.get_or_fetch_kline("AAPL", kline_t="1D", limit=20)

    assert response is not None
    assert response.symbol == "AAPL"
    assert response.bars[0].close == 100
    assert store.load_all("AAPL")[0]["bar_time"] == "2026-06-20"
    assert client.stocks.calls == [("get_all_klines_with_df", {})]


@pytest.mark.asyncio
async def test_kline_batch_calls_single_symbol_sdk_contract() -> None:
    import pandas as pd

    def rows() -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "symbol": symbol,
                    "bar_time": "2026-06-20",
                    "open": 1,
                    "high": 2,
                    "low": 1,
                    "close": 2,
                }
                for symbol in ["AAPL", "MSFT"]
            ]
        )

    client = FakeDojo(stocks={"get_all_klines_with_df": rows})
    store = KlineStore(client, StockStore(client), StockSectorStore(client))

    result = await store.get_klines(["AAPL", "MSFT"], limit=15)

    assert set(result.items) == {"AAPL", "MSFT"}
    assert client.stocks.calls == [
        ("get_all_klines_with_df", {}),
    ]


@pytest.mark.asyncio
async def test_kline_stats_reports_memory_state() -> None:
    client = FakeDojo()
    store = KlineStore(client, StockStore(client), StockSectorStore(client))
    import pandas as pd

    store._in_memory_updates = {
        "AAPL": pd.DataFrame([{"symbol": "AAPL", "bar_time": "2026-06-20"}]),
        "MSFT": pd.DataFrame(),
    }
    store._cache = {"AAPL_None_None_None_None_252": "dummy"}
    store.member_symbols = 2

    stats = await store.stats()

    assert stats.member_symbols == 2
    assert stats.tracked_symbols == 2
    assert stats.loaded_symbols == 1
    assert stats.initial_load_in_progress is False


@pytest.mark.asyncio
async def test_kline_store_exposes_load_contract() -> None:
    client = FakeDojo()
    store = KlineStore(client, StockStore(client), StockSectorStore(client))

    assert inspect.iscoroutinefunction(store.load)


@pytest.mark.asyncio
async def test_sector_klines_group_cached_rows_by_scope(monkeypatch) -> None:
    client = FakeDojo()
    store = KlineStore(client, StockStore(client), StockSectorStore(client))
    import pandas as pd

    store._in_memory_updates = {
        symbol: pd.DataFrame(
            [
                {
                    "symbol": symbol,
                    "bar_time": "2026-06-20",
                    "open": 1,
                    "high": 2,
                    "low": 1,
                    "close": 2,
                }
            ]
        )
        for symbol in ("L1", "L2", "L3")
    }
    monkeypatch.setattr(
        kline_store_module,
        "collect_sector_scope_tickers",
        lambda *_args, **_kwargs: {
            "L1": {"L1", "L2", "L3"},
            "L2": {"L2", "L3"},
            "L3": {"L3"},
        },
    )

    result = await store.get_sector_klines(_sector_path(), market="us")

    assert result.scopes["L3"].symbols == ["L3"]
    assert result.scopes["L2"].loaded_symbols == 2
    assert result.scopes["L1"].loaded_symbols == 3


@pytest.mark.asyncio
async def test_prioritize_sector_path_fetches_l3_then_l2_then_l1(monkeypatch) -> None:
    client = FakeDojo()
    store = KlineStore(client, StockStore(client), StockSectorStore(client))
    calls: list[list[str]] = []
    monkeypatch.setattr(
        kline_store_module,
        "collect_sector_scope_tickers",
        lambda *_args, **_kwargs: {
            "L1": {"L1", "L2", "L3"},
            "L2": {"L2", "L3"},
            "L3": {"L3"},
        },
    )

    async def record(symbols: list[str], limit: int = 252) -> ConstituentKlineBatchResponse:
        del limit
        calls.append(symbols)
        return ConstituentKlineBatchResponse()

    monkeypatch.setattr(store, "get_klines", record)

    await store.prioritize_sector_path(_sector_path(), market="us")

    assert calls == [["L3"], ["L2"], ["L1"]]


@pytest.mark.asyncio
async def test_initial_holding_shares_awaits_market_cap_allocation() -> None:
    client = FakeDojo()
    stocks = StockStore(client)
    stock = _quoted_stock()
    stocks.by_ticker["us:AAPL"] = stock

    shares = await initial_shares_for_new_holding(stocks, [], "us", "AAPL", capital=1_000.0)

    assert shares == 10


@pytest.mark.asyncio
async def test_portfolio_create_returns_resolved_detail(tmp_path) -> None:
    client = FakeDojo()
    service = PortfolioService(
        PortfolioStore(tmp_path),
        StockStore(client),
        StockSectorStore(client),
        KlineStore(client, StockStore(client), StockSectorStore(client)),
    )

    result = await service.create(CreatePortfolioRequest(name="Long Term"))

    assert isinstance(result, PortfolioDetail)
    assert result.name == "Long Term"
