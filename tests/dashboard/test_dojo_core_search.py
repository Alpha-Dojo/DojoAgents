from __future__ import annotations

from dojoagents.dashboard.schemas.stock import Stock, StockQuote
from dojoagents.dashboard.services.dojo_core_search import search_core_tickers
from dojoagents.dashboard.services.stock_quote_filter import (
    configure_ticker_market_cap_mins,
    stock_passes_ticker_market_cap_min,
)


def _quote(*, ticker: str, market_cap: float, volume: int = 1_000) -> StockQuote:
    return StockQuote(
        ticker=ticker,
        name=ticker,
        last_price=10.0,
        pre_close=9.9,
        open=10.0,
        high=10.5,
        low=9.8,
        change=0.1,
        change_percent=1.0,
        volume=volume,
        amount=1e6,
        avg_price=10.0,
        market_cap=market_cap,
        turn_rate=0.5,
        pe=15.0,
        pb=2.0,
        dividend_yield=0.0,
    )


def _stock(*, ticker: str, market: str = "us", market_cap: float) -> Stock:
    return Stock(
        ticker=ticker,
        market=market,
        short_name=ticker,
        stock_quote=_quote(ticker=ticker, market_cap=market_cap),
    )


class _FakeStockStore:
    def __init__(self, stocks: list[Stock]) -> None:
        self._by_market: dict[str, list[Stock]] = {"sh": [], "hk": [], "us": []}
        self._by_ticker: dict[str, Stock] = {}
        for stock in stocks:
            self._by_market.setdefault(stock.market, []).append(stock)
            self._by_ticker[stock.ticker.upper()] = stock

    def list_market(self, market: str) -> list[Stock]:
        return list(self._by_market.get(market, []))

    def resolve(self, ticker: str, market: str | None = None) -> Stock | None:
        return self._by_ticker.get(ticker.strip().upper())

    def is_ticker_market_cap_eligible(self, ticker: str, market: str | None = None) -> bool:
        stock = self.resolve(ticker, market=market)
        if stock is None:
            return False
        return stock_passes_ticker_market_cap_min(stock)


def test_search_skips_below_market_cap_floor_by_default() -> None:
    configure_ticker_market_cap_mins(sh=1e9, us=1e9, hk=1e9)
    store = _FakeStockStore(
        [
            _stock(ticker="AAPL", market_cap=3e12),
            _stock(ticker="VIVK", market_cap=5e7),
        ]
    )

    items = search_core_tickers(store, None, None, "VIVK", market="us")
    assert [item.ticker for item in items] == []


def test_search_includes_below_market_cap_floor_when_disabled() -> None:
    configure_ticker_market_cap_mins(sh=1e9, us=1e9, hk=1e9)
    store = _FakeStockStore(
        [
            _stock(ticker="AAPL", market_cap=3e12),
            _stock(ticker="VIVK", market_cap=5e7),
        ]
    )

    items = search_core_tickers(
        store,
        None,
        None,
        "VIVK",
        market="us",
        require_market_cap_eligible=False,
    )
    assert [item.ticker for item in items] == ["VIVK"]


def test_search_dedupes_duplicate_store_rows() -> None:
    configure_ticker_market_cap_mins(sh=1e9, us=1e9, hk=1e9)
    store = _FakeStockStore(
        [
            _stock(ticker="VIK", market_cap=2e10),
            _stock(ticker="VIK", market_cap=2e10),
            _stock(ticker="VICI", market_cap=3e10),
            _stock(ticker="VICI", market_cap=3e10),
        ]
    )

    items = search_core_tickers(
        store,
        None,
        None,
        "VI",
        market="us",
        require_market_cap_eligible=False,
    )
    assert [item.ticker for item in items] == ["VICI", "VIK"]
