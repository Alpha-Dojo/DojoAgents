from __future__ import annotations

import math

from dojoagents.dashboard.schemas.stock import Stock

MARKETS = ("sh", "hk", "us")

# Minimum ticker market_cap from stock_quote; tickers at or below are excluded
# from sector precompute weighting / member_count, constituent lists, and
# performance curves (sector *total-cap* ranking floors are separate).
DEFAULT_TICKER_MARKET_CAP_MIN_BY_MARKET: dict[str, float] = {
    "sh": 1e9,  # 10 亿
    "us": 1e9,  # 10 亿
    "hk": 1e9,  # 10 亿
}

_CAP_MINS: dict[str, float] = dict(DEFAULT_TICKER_MARKET_CAP_MIN_BY_MARKET)


def configure_ticker_market_cap_mins(*, sh: float, us: float, hk: float) -> None:
    """Apply dashboard financial config thresholds (call once at app startup)."""
    global _CAP_MINS
    _CAP_MINS = {"sh": float(sh), "us": float(us), "hk": float(hk)}


def ticker_market_cap_min(market: str) -> float | None:
    return _CAP_MINS.get(market.lower())


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


def stock_has_trading_activity(stock: Stock) -> bool:
    """True when the session quote shows volume, amount, or turnover."""
    quote = stock.stock_quote
    if quote is None:
        return False
    if quote.volume > 0:
        return True
    if (quote.amount or 0) > 0:
        return True
    if quote.turn_rate > 0:
        return True
    return False


def stock_is_delisted(stock: Stock) -> bool:
    return stock.is_delisted is True


def stock_passes_market_screen_hard_filters(stock: Stock) -> bool:
    """Hard eligibility for full-market screen: quoted, listed, traded, positive cap."""
    quote = stock.stock_quote
    if quote is None:
        return False
    if stock_is_delisted(stock):
        return False
    if quote.market_cap <= 0:
        return False
    if not stock_has_trading_activity(stock):
        return False
    return True


def effective_min_market_cap(market: str, min_market_cap: float | None) -> float | None:
    """Use configured floor when caller omits min_market_cap; explicit 0 disables the floor."""
    if min_market_cap is not None:
        return min_market_cap
    return ticker_market_cap_min(market)


def passes_market_cap_floor(market: str, market_cap: float | None, *, min_market_cap: float | None) -> bool:
    threshold = effective_min_market_cap(market, min_market_cap)
    if threshold is None or threshold <= 0:
        return True
    if market_cap is None or market_cap <= threshold:
        return False
    return True


def change_significance_score(change_percent: float | None, market_cap: float | None) -> float:
    """Rank movers by change weighted with log(market_cap); raw change when cap missing."""
    if change_percent is None:
        return float("-inf")
    if market_cap is None or market_cap <= 0:
        return float(change_percent)
    return float(change_percent) * math.log(float(market_cap))


def stock_passes_ticker_market_cap_min(stock: Stock) -> bool:
    quote = stock.stock_quote
    if quote is None:
        return False
    if not stock_has_quote_volume(stock):
        return False
    return passes_ticker_market_cap_min(stock.market, quote.market_cap)
