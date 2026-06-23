"""Eligibility rules for sector index constituents."""

from __future__ import annotations

from dojoagents.dashboard.services.kline_store import KlineStore
from dojoagents.dashboard.schemas.stock import Stock

RECENT_VOLUME_LOOKBACK = 20


def _quote_has_trading_activity(stock: Stock) -> bool:
    quote = stock.quote
    if quote is None:
        return False
    if quote.volume > 0:
        return True
    if (quote.amount or 0) > 0:
        return True
    if quote.turn_rate > 0:
        return True
    return False


def is_sector_constituent_eligible(
    stock: Stock | None,
    kline_store: KlineStore,
) -> bool:
    """Sector index constituents must have daily klines and recent trading volume."""
    if stock is None or stock.quote is None:
        return False
    if stock.quote.market_cap <= 0:
        return False

    bars = kline_store.get_stock_kline(stock.ticker, limit=RECENT_VOLUME_LOOKBACK)
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

    def is_eligible(self, stock: Stock | None) -> bool:
        if stock is None:
            return False
        key = (stock.market, stock.ticker)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        eligible = is_sector_constituent_eligible(stock, self._kline_store)
        self._cache[key] = eligible
        return eligible
