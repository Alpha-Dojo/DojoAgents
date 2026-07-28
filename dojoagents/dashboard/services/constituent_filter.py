"""Eligibility rules for sector index constituents."""

from __future__ import annotations

from dojoagents.dashboard.services.kline_store import KlineStore
from dojoagents.dashboard.schemas.stock import Stock
from dojoagents.dashboard.services.stock_quote_filter import stock_passes_ticker_market_cap_min

RECENT_VOLUME_LOOKBACK = 20
ALLOWED_SECTOR_QUOTE_TYPE = "EQUITY"


def stock_is_equity_quote_type(stock: Stock) -> bool:
    """True when stock_info ``quote_type`` is EQUITY (sector index universe only)."""
    return str(stock.quote_type or "").strip().upper() == ALLOWED_SECTOR_QUOTE_TYPE


def stock_is_us_warrant_by_name(stock: Stock) -> bool:
    """True when a US listing's display name contains ``Warrant`` (case-insensitive).

    Yahoo-style equity metadata labels warrants as EQUITY, so name text is the
    reliable signal. Applied only to ``market == us`` to avoid CN false positives
    (e.g. company names containing the English word Warrant).
    """
    if str(stock.market or "").strip().lower() != "us":
        return False
    parts = [stock.short_name or "", stock.long_name or ""]
    quote = stock.stock_quote
    if quote is not None and quote.name:
        parts.append(quote.name)
    return "warrant" in " ".join(parts).lower()


def _quote_has_trading_activity(stock: Stock) -> bool:
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


async def is_sector_constituent_eligible(
    stock: Stock | None,
    kline_store: KlineStore,
) -> bool:
    """Sector index constituents must be EQUITY, clear the ticker cap floor, have klines, and trade."""
    if stock is None or stock.stock_quote is None:
        return False
    if not stock_is_equity_quote_type(stock):
        return False
    if stock_is_us_warrant_by_name(stock):
        return False
    if stock.stock_quote.market_cap <= 0:
        return False
    # Same ~10亿 floor as constituent lists / performance curves.
    if not stock_passes_ticker_market_cap_min(stock):
        return False

    response = await kline_store.get_or_fetch_kline(
        stock.ticker,
        market=stock.market,
        limit=RECENT_VOLUME_LOOKBACK,
    )
    if response is None:
        return False
    bars = response.bars
    if not bars or bars[-1].close <= 0:
        return False
    if _quote_has_trading_activity(stock):
        return True
    return any(bar.vol > 0 for bar in bars)


class ConstituentEligibilityChecker:
    """Memoize eligibility per (market, ticker) within a process lifetime."""

    def __init__(self, kline_store: KlineStore) -> None:
        self._kline_store = kline_store
        self._cache: dict[tuple[str, str], bool] = {}

    async def is_eligible(self, stock: Stock | None) -> bool:
        if stock is None:
            return False
        key = (stock.market, stock.ticker)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        eligible = await is_sector_constituent_eligible(stock, self._kline_store)
        self._cache[key] = eligible
        return eligible
