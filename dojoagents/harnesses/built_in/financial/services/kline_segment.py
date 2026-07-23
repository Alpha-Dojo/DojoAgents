from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, List, Optional

from dojoagents.harnesses.built_in.financial.contracts.stock_kline import StockKlineBar

# Split kline history when bars are farther apart (e.g. ticker reuse after delisting).
MAX_BAR_GAP_DAYS = 30
WINDOW_HISTORY_DAYS = 365
# Cap-weighted sector daily returns exclude single-name outliers above this gain.
MAX_SECTOR_MEMBER_DAILY_RETURN = 0.50


def _parse_day(value: str) -> date:
    return datetime.strptime(value[:10], "%Y-%m-%d").date()


def bar_day(bar: StockKlineBar) -> str:
    return str(bar.bar_time)[:10]


def latest_segment_bars(
    bars: List[StockKlineBar],
    *,
    max_gap_days: int = MAX_BAR_GAP_DAYS,
) -> List[StockKlineBar]:
    """Keep only the most recent contiguous trading segment."""
    valid = [bar for bar in bars if bar.close is not None and bar.close > 0]
    if not valid:
        return []

    valid.sort(key=bar_day)

    latest_segment = [valid[-1]]
    prev_day = _parse_day(bar_day(valid[-1]))

    for bar in reversed(valid[:-1]):
        curr_day = _parse_day(bar_day(bar))
        if (prev_day - curr_day).days > max_gap_days:
            break
        latest_segment.append(bar)
        prev_day = curr_day

    latest_segment.reverse()
    return latest_segment


@dataclass(frozen=True)
class SegmentOHLC:
    closes: Dict[str, float]
    opens: Dict[str, float]
    first_date: str
    first_open: float
    last_date: str
    prev_closes: Dict[str, float]


def latest_segment_ohlc(bars: List[StockKlineBar]) -> Optional[SegmentOHLC]:
    segment = latest_segment_bars(bars)
    if not segment:
        return None

    closes: Dict[str, float] = {}
    opens: Dict[str, float] = {}
    prev_closes: Dict[str, float] = {}

    prev_close = None
    for bar in segment:
        day = bar_day(bar)
        close_val = float(bar.close)
        closes[day] = close_val
        if prev_close is not None:
            prev_closes[day] = prev_close
        prev_close = close_val
        if bar.open is not None and bar.open > 0:
            opens[day] = float(bar.open)

    if not closes:
        return None

    first_date = min(closes)
    last_date = max(closes)
    first_open = opens.get(first_date)
    if first_open is None or first_open <= 0:
        first_open = closes[first_date]

    return SegmentOHLC(
        closes=closes,
        opens=opens,
        first_date=first_date,
        first_open=first_open,
        last_date=last_date,
        prev_closes=prev_closes,
    )


def listing_span_days(first_date: str, last_date: str) -> int:
    return (_parse_day(last_date) - _parse_day(first_date)).days


def member_daily_return(
    *,
    date: str,
    close: float,
    first_date: str,
    prev_closes: Dict[str, float],
    opens: Dict[str, float],
) -> Optional[float]:
    """
    Daily return for one member on ``date``.

    - Listing day: close / open - 1
    - Later days: close / previous close - 1 (within the same segment)
    """
    if close <= 0:
        return None

    if date == first_date:
        open_price = opens.get(date)
        if open_price is None or open_price <= 0:
            open_price = close
        return close / open_price - 1

    prev_close = prev_closes.get(date)
    if prev_close is None or prev_close <= 0:
        return None
    return close / prev_close - 1


def sector_member_daily_return_usable(daily_return: float) -> bool:
    """True when a constituent daily return may contribute to sector averages."""
    return daily_return <= MAX_SECTOR_MEMBER_DAILY_RETURN
