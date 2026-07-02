from __future__ import annotations

from types import SimpleNamespace

import pytest

from dojoagents.dashboard.schemas.stock_kline import StockKlineBar
from dojoagents.dashboard.services.domain_api import build_ticker_price_trends_v1


class KlineStore:
    async def get_or_fetch_kline(self, *_args, **_kwargs):
        return SimpleNamespace(
            symbol="AAPL",
            as_of="2026-06-20",
            source="computed",
            stale=False,
            bars=[
                StockKlineBar(
                    symbol="AAPL",
                    bar_time="2026-06-20",
                    open=100,
                    high=101,
                    low=99,
                    close=100,
                )
            ],
        )


class FinStore:
    async def get_for_ticker(self, *_args, **_kwargs):
        raise ValueError("upstream unavailable")


class StockStore:
    def resolve(self, ticker, market=None):
        if ticker == "AAPL":
            return SimpleNamespace(ticker="AAPL", market="us")
        return None

    def find_market(self, _ticker):
        return "us"

    def get(self, _market, _ticker):
        quote = SimpleNamespace(total_shares=10, market_cap=1000, last_price=100)
        return SimpleNamespace(stock_quote=quote)


@pytest.mark.asyncio
async def test_price_trends_defaults_start_date_to_dashboard_inception() -> None:
    captured: dict[str, object] = {}

    class KlineStore:
        async def get_or_fetch_kline(self, symbol, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                symbol=symbol,
                as_of="2026-06-30",
                source="computed",
                stale=False,
                bars=[
                    StockKlineBar(
                        symbol=symbol,
                        bar_time="2025-01-02",
                        open=500,
                        high=510,
                        low=490,
                        close=505,
                    )
                ],
            )

    class FinStore:
        async def get_for_ticker(self, *_args, **_kwargs):
            raise ValueError("upstream unavailable")

    class StockStore:
        def resolve(self, ticker, market=None):
            if ticker == "0700.HK" and market == "hk":
                return SimpleNamespace(ticker="0700.HK", market="hk")
            return None

        def get(self, market, ticker):
            if market == "hk" and ticker == "0700.HK":
                return SimpleNamespace(
                    ticker="0700.HK",
                    market="hk",
                    stock_quote=SimpleNamespace(total_shares=1, market_cap=1, last_price=500),
                )
            return None

        def find_market(self, _ticker):
            return None

    registry = SimpleNamespace(
        kline_store=KlineStore(),
        stock_fin_indicators_store=FinStore(),
        stock_store=StockStore(),
    )

    response = await build_ticker_price_trends_v1(
        registry,
        ticker="0700.HK",
        market="hk",
        start_date=None,
        end_date=None,
        limit=None,
    )

    assert response is not None
    assert captured["start_time"] == "2025-01-01"
    assert captured["limit"] == 0


@pytest.mark.asyncio
async def test_price_trends_resolves_hk_symbol_via_stock_store() -> None:
    captured: dict[str, str] = {}

    class KlineStore:
        async def get_or_fetch_kline(self, symbol, **_kwargs):
            captured["symbol"] = symbol
            return SimpleNamespace(
                symbol=symbol,
                as_of="2026-06-20",
                source="computed",
                stale=False,
                bars=[
                    StockKlineBar(
                        symbol=symbol,
                        bar_time="2026-06-20",
                        open=500,
                        high=510,
                        low=490,
                        close=505,
                    )
                ],
            )

    class FinStore:
        async def get_for_ticker(self, *_args, **_kwargs):
            raise ValueError("upstream unavailable")

    class StockStore:
        def resolve(self, ticker, market=None):
            if ticker == "0700.HK" and market == "hk":
                return SimpleNamespace(ticker="0700.HK", market="hk")
            return None

        def get(self, market, ticker):
            if market == "hk" and ticker == "0700.HK":
                return SimpleNamespace(
                    ticker="0700.HK",
                    market="hk",
                    stock_quote=SimpleNamespace(total_shares=1, market_cap=1, last_price=500),
                )
            return None

        def find_market(self, _ticker):
            return None

    registry = SimpleNamespace(
        kline_store=KlineStore(),
        stock_fin_indicators_store=FinStore(),
        stock_store=StockStore(),
    )

    response = await build_ticker_price_trends_v1(
        registry,
        ticker="0700",
        market="hk",
        start_date=None,
        end_date=None,
        limit=30,
    )

    assert response is not None
    assert captured["symbol"] == "0700.HK"
    assert response.ticker == "0700.HK"
    assert response.market == "hk"


@pytest.mark.asyncio
async def test_price_trends_returns_kline_even_when_financials_fail() -> None:
    registry = SimpleNamespace(
        kline_store=KlineStore(),
        stock_fin_indicators_store=FinStore(),
        stock_store=StockStore(),
    )

    response = await build_ticker_price_trends_v1(
        registry,
        ticker="AAPL",
        market="us",
        start_date=None,
        end_date=None,
        limit=30,
    )

    assert response is not None
    assert response.ticker == "AAPL"
    assert len(response.bars) == 1
    assert response.pe_points == []
