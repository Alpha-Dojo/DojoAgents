from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from dojoagents.dashboard.services.kline_bar_utils import DATA_START_DATE
from dojoagents.dashboard.services.kline_store import KlineStore

_KLINE_RECENT_LOOKBACK_DAYS = 60
_US_KLINE_SYMBOL_FALLBACKS: dict[str, list[str]] = {
    "GOOGL": ["GOOG"],
    "GOOG": ["GOOGL"],
}


def kline_symbol_candidates(symbol: str) -> list[str]:
    canonical = symbol.strip().upper()
    candidates = [canonical]
    for alternate in _US_KLINE_SYMBOL_FALLBACKS.get(canonical, []):
        if alternate not in candidates:
            candidates.append(alternate)
    return candidates


async def fetch_kline_bars_for_symbol(
    kline_store: KlineStore,
    *,
    symbol: str,
    market: str,
    order_time: str | None = None,
    user_price: float | None = None,
    after_date: str | None = None,
) -> list[Any]:
    """Fetch kline bars with explicit date windows instead of trailing tail limits."""
    today = date.today().isoformat()
    if order_time:
        response = await kline_store.get_or_fetch_kline(
            symbol,
            market=market,
            start_time=order_time,
            end_time=order_time,
        )
        return list(response.bars) if response is not None else []

    if user_price is not None:
        response = await kline_store.get_or_fetch_kline(
            symbol,
            market=market,
            start_time=DATA_START_DATE,
            end_time=today,
        )
        return list(response.bars) if response is not None else []

    if after_date:
        response = await kline_store.get_or_fetch_kline(
            symbol,
            market=market,
            start_time=after_date,
            end_time=today,
        )
        return list(response.bars) if response is not None else []

    recent_start = (date.today() - timedelta(days=_KLINE_RECENT_LOOKBACK_DAYS)).isoformat()
    response = await kline_store.get_or_fetch_kline(
        symbol,
        market=market,
        start_time=recent_start,
        end_time=today,
    )
    return list(response.bars) if response is not None else []


async def fetch_kline_bars_with_symbol_fallback(
    kline_store: KlineStore,
    *,
    symbol: str,
    market: str,
    order_time: str | None = None,
    user_price: float | None = None,
    after_date: str | None = None,
) -> tuple[list[Any], str]:
    for candidate in kline_symbol_candidates(symbol):
        bars = await fetch_kline_bars_for_symbol(
            kline_store,
            symbol=candidate,
            market=market,
            order_time=order_time,
            user_price=user_price,
            after_date=after_date,
        )
        if bars:
            return bars, candidate
    return [], symbol.strip().upper()
