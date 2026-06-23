from __future__ import annotations

from typing import Dict, Optional

from dojoagents.dashboard.services.kline_segment import (
    WINDOW_HISTORY_DAYS,
    latest_segment_ohlc,
    listing_span_days,
)
from dojoagents.dashboard.services.stock_store import StockStore
from dojoagents.dashboard.schemas.stock_kline import StockKlineResponse


def close_at_window_start(closes: Dict[str, float], window_start: str) -> Optional[float]:
    """Forward-fill to window start, matching sector index seeding at unified start."""
    if not closes or not window_start:
        return None

    last_on_or_before: Optional[float] = None
    for day in sorted(closes):
        if day <= window_start:
            last_on_or_before = closes[day]
        else:
            break
    if last_on_or_before is not None:
        return last_on_or_before

    for day in sorted(closes):
        if day >= window_start:
            return closes[day]
    return None


def resolve_window_return_base(
    *,
    closes: Dict[str, float],
    first_date: str,
    first_open: float,
    last_date: str,
    window_start: str,
) -> Optional[float]:
    """
    Base price for window return.

    When history is shorter than 1Y or listing is after the unified window start,
    anchor on the listing-day open. Otherwise use the close at window start.
    """
    if first_open <= 0:
        return None

    short_history = listing_span_days(first_date, last_date) < WINDOW_HISTORY_DAYS
    listed_after_window = bool(window_start and first_date > window_start)
    if short_history or listed_after_window:
        return first_open

    return close_at_window_start(closes, window_start)


def compute_constituent_window_change_percent(
    *,
    stock_store: StockStore,
    kline: StockKlineResponse | None,
    ticker: str,
    market: str,
    window_start: str,
) -> Optional[float]:
    """Total return since the performance-curve unified window start (%)."""
    if not window_start:
        return None

    stock = stock_store.get(market, ticker)
    if stock is None or stock.stock_quote is None:
        return None

    last_price = stock.stock_quote.last_price
    if last_price is None or last_price <= 0:
        return None

    if kline is None or not kline.bars:
        return None

    segment = latest_segment_ohlc(kline.bars)
    if segment is None:
        return None

    base_price = resolve_window_return_base(
        closes=segment.closes,
        first_date=segment.first_date,
        first_open=segment.first_open,
        last_date=segment.last_date,
        window_start=window_start,
    )
    if base_price is None or base_price <= 0:
        return None

    return round((last_price / base_price - 1) * 100, 2)


def compute_constituent_trading_window_change_percent(
    *,
    stock_store: StockStore,
    kline: StockKlineResponse | None,
    ticker: str,
    market: str,
    days: int,
) -> Optional[float]:
    """Total return over the most recent N trading bars."""
    if days < 1:
        return None
    stock = stock_store.get(market, ticker)
    if stock is None or stock.stock_quote is None:
        return None
    last_price = stock.stock_quote.last_price
    if last_price is None or last_price <= 0:
        return None
    if kline is None or not kline.bars:
        return None
    segment = latest_segment_ohlc(kline.bars)
    if segment is None or not segment.closes:
        return None
    ordered_days = sorted(segment.closes)
    start_index = max(0, len(ordered_days) - 1 - days)
    base_day = ordered_days[start_index]
    base_price = close_at_window_start(segment.closes, base_day)
    if base_price is None or base_price <= 0:
        return None
    return round((last_price / base_price - 1) * 100, 2)
