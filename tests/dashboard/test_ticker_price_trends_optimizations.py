from __future__ import annotations

from types import SimpleNamespace

import pytest

from dojoagents.dashboard.schemas.stock_kline import StockKlineBar
from dojoagents.dashboard.services.domain_api import _resolve_kline_symbol, build_ticker_price_trends_v1


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
    captured: list[dict[str, object]] = []

    class KlineStore:
        async def get_or_fetch_kline(self, symbol, **kwargs):
            captured.append(dict(kwargs))
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
    assert captured[0].get("start_time") is None
    assert captured[0].get("min_bar_time") == "2025-01-01"
    assert captured[0].get("limit") is None


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
async def test_resolve_kline_symbol_adds_ashare_and_hk_suffixes() -> None:
    class StockStore:
        def resolve(self, ticker, market=None):
            if ticker == "688008.SS" and (market is None or market == "sh"):
                return SimpleNamespace(ticker="688008.SS", market="sh")
            if ticker == "0700.HK" and (market is None or market == "hk"):
                return SimpleNamespace(ticker="0700.HK", market="hk")
            return None

        def get(self, market, ticker):
            return self.resolve(ticker, market=market)

        def find_market(self, _ticker):
            return None

    store = StockStore()
    assert _resolve_kline_symbol(store, "688008", "cn") == ("688008.SS", "sh")
    assert _resolve_kline_symbol(store, "688008", "sh") == ("688008.SS", "sh")
    assert _resolve_kline_symbol(store, "0700", "hk") == ("0700.HK", "hk")
    assert _resolve_kline_symbol(None, "688008", "cn") == ("688008.SS", "sh")


@pytest.mark.asyncio
async def test_price_trends_pe_band_matches_kline_date_window(monkeypatch) -> None:
    captured_bars: list[object] = []

    async def fake_pe_band(_ticker, *, bars=None, **_kwargs):
        captured_bars.extend(bars or [])
        return None

    monkeypatch.setattr(
        "dojoagents.dashboard.services.domain_api.resolve_core_ticker_pe_band",
        fake_pe_band,
    )

    class KlineStore:
        async def get_or_fetch_kline(self, symbol, **kwargs):
            assert kwargs.get("start_time") == "2026-06-18"
            assert kwargs.get("end_time") == "2026-06-18"
            return SimpleNamespace(
                symbol=symbol,
                as_of="2026-06-18",
                source="computed",
                stale=False,
                bars=[
                    StockKlineBar(
                        symbol=symbol,
                        bar_time="2026-06-18",
                        open=363.89,
                        high=369.0,
                        low=356.61,
                        close=367.46,
                    )
                ],
            )

    class FinStore:
        async def get_for_ticker(self, *_args, **_kwargs):
            raise ValueError("upstream unavailable")

    class StockStore:
        def resolve(self, ticker, market=None):
            if ticker == "GOOG":
                return SimpleNamespace(ticker="GOOG", market="us")
            return None

        def find_market(self, _ticker):
            return "us"

        def get(self, _market, _ticker):
            quote = SimpleNamespace(total_shares=10, market_cap=1000, last_price=100)
            return SimpleNamespace(stock_quote=quote)

    registry = SimpleNamespace(
        kline_store=KlineStore(),
        stock_fin_indicators_store=FinStore(),
        stock_store=StockStore(),
    )

    response = await build_ticker_price_trends_v1(
        registry,
        ticker="GOOG",
        market="us",
        start_date="2026-06-18",
        end_date="2026-06-18",
        limit=None,
    )

    assert response is not None
    assert len(response.klines) == 1
    assert len(captured_bars) == 1
    assert captured_bars[0].bar_time == "2026-06-18"


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
