from __future__ import annotations

from functools import lru_cache

from dojoagents.dashboard.schemas.stock import Stock

MARKETS = ("sh", "hk", "us")

# Minimum ticker market_cap from stock_quote; tickers at or below are excluded
# from sector change weighting and kline fetch (sectors themselves are not filtered).
DEFAULT_TICKER_MARKET_CAP_MIN_BY_MARKET: dict[str, float] = {
    "sh": 1e9,  # 10 亿
    "us": 1e9,  # 10 亿
    "hk": 1e9,  # 10 亿
}


@lru_cache
def _settings_caps() -> dict[str, float]:
    return DEFAULT_TICKER_MARKET_CAP_MIN_BY_MARKET.copy()


def ticker_market_cap_min(market: str) -> float | None:
    return _settings_caps().get(market.lower())


def passes_ticker_market_cap_min(market: str, market_cap: float) -> bool:
    """True when stock_quote.market_cap is above the per-market minimum."""
    threshold = ticker_market_cap_min(market)
    if threshold is None:
        return True
    return market_cap > threshold


def stock_has_quote_volume(stock: Stock) -> bool:
    """True when current_quote reports non-zero trading volume."""
    quote = stock.stock_quote
    if quote is None:
        return False
    return quote.volume > 0


def stock_passes_ticker_market_cap_min(stock: Stock) -> bool:
    quote = stock.stock_quote
    if quote is None:
        return False
    if not stock_has_quote_volume(stock):
        return False
    return passes_ticker_market_cap_min(stock.market, quote.market_cap)
