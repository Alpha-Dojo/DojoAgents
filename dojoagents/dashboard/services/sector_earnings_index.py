from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Protocol, Set, Tuple
from zoneinfo import ZoneInfo

from dojoagents.dashboard.services.kline_segment import (
    latest_segment_ohlc,
    member_daily_return,
    sector_member_daily_return_usable,
)
from dojoagents.dashboard.services.stock_quote_filter import stock_passes_ticker_market_cap_min
from dojoagents.dashboard.services.stock_store import StockStore
from dojoagents.dashboard.schemas.stock import Stock
from dojoagents.dashboard.schemas.stock_kline import StockKlineBar, StockKlineResponse

INDEX_BASE = 100.0
PRE_CLOSE_MATCH_TOLERANCE = 0.002

MARKET_TIMEZONES: Dict[str, str] = {
    "sh": "Asia/Shanghai",
    "hk": "Asia/Shanghai",
    "us": "America/New_York",
}

# Regular cash session open (local time). Quote supplement only after the open.
MARKET_REGULAR_OPEN: Dict[str, Tuple[int, int]] = {
    "us": (9, 30),
    "sh": (9, 30),
    "hk": (9, 30),
}


class KlineStoreReader(Protocol):
    async def get_kline(self, symbol: str) -> Any: ...  # noqa
    async def get_klines(self, symbols: List[str]) -> Any: ...  # noqa


@dataclass(frozen=True)
class _IndexMember:
    weight: float
    closes: Dict[str, float]
    opens: Dict[str, float]
    first_date: str
    first_open: float
    base_close: float
    prev_closes: Dict[str, float]


def market_cap_weight(stock) -> Optional[float]:
    """Market-cap weight for sector return / index aggregation."""
    quote = stock.stock_quote
    if quote is None or quote.market_cap <= 0:
        return None
    return quote.market_cap


def market_cap_weighted_quote_change(
    *,
    change_percent: float,
    market_cap: float,
) -> Optional[Tuple[float, float]]:
    """Return (weight, weighted_change_contribution) when market cap is valid."""
    if market_cap <= 0:
        return None
    return market_cap, market_cap * change_percent


def stock_passes_sector_performance_weight(stock: Stock) -> bool:
    """DojoSphere index eligibility: cap/volume filter (same as DojoMesh)."""
    return stock_passes_ticker_market_cap_min(stock)


def filter_cap_weighted_tickers(
    market: str,
    tickers: Set[str],
    stock_store: StockStore,
) -> Set[str]:
    """Constituents eligible for market-cap-weighted sector performance curves."""
    eligible: Set[str] = set()
    for ticker in tickers:
        if stock_store.find_market(ticker) != market:
            continue
        stock = stock_store.get(market, ticker)
        if stock is not None and stock_passes_sector_performance_weight(stock):
            eligible.add(ticker)
    return eligible


def latest_one_day_index_return(series: List[Tuple[str, float]]) -> Optional[float]:
    """One-day percent return between the last two index levels."""
    if len(series) < 2:
        return None
    prev = series[-2][1]
    last = series[-1][1]
    if prev <= 0:
        return None
    return round((last / prev - 1) * 100, 2)


def _bar_date(bar: StockKlineBar) -> str:
    return str(bar.bar_time)[:10]


def _parse_iso_date(value: str) -> date:
    return datetime.strptime(value[:10], "%Y-%m-%d").date()


def _is_weekday(d: date) -> bool:
    return d.weekday() < 5


def _is_plausible_live_session_date(session_date: str, kline_date: str) -> bool:
    """
    True when session_date could be the next trading session after kline_date.

    Rejects weekends and calendar gaps too large for a single session advance
    (e.g. Fri close viewed on Sun is not a live Sun session).
    """
    session_d = _parse_iso_date(session_date)
    if not _is_weekday(session_d):
        return False
    if not kline_date:
        return True
    kline_d = _parse_iso_date(kline_date)
    gap = (session_d - kline_d).days
    if gap < 1:
        return False
    # Fri→Mon is 3 calendar days; allow slack for holiday-adjacent sessions.
    return gap <= 4


def market_local_datetime(market: str, *, now: Optional[datetime] = None) -> datetime:
    tz_name = MARKET_TIMEZONES.get(market, "UTC")
    if now is None:
        return datetime.now(ZoneInfo(tz_name))
    return now.astimezone(ZoneInfo(tz_name))


def market_local_date(market: str, *, now: Optional[datetime] = None) -> str:
    return market_local_datetime(market, now=now).date().isoformat()


def market_regular_session_has_started(market: str, *, now: Optional[datetime] = None) -> bool:
    """True after the market's regular session open on its local calendar day."""
    local = market_local_datetime(market, now=now)
    open_hour, open_minute = MARKET_REGULAR_OPEN.get(market, (9, 30))
    open_at = local.replace(hour=open_hour, minute=open_minute, second=0, microsecond=0)
    return local >= open_at


def _pre_close_matches_kline(pre_close: float, kline_close: float) -> bool:
    if pre_close <= 0 or kline_close <= 0:
        return False
    return abs(pre_close - kline_close) / kline_close <= PRE_CLOSE_MATCH_TOLERANCE


def _latest_kline_close(kline: StockKlineResponse | None) -> Tuple[str, float]:
    if kline is None or not kline.bars:
        return "", 0.0
    closes: Dict[str, float] = {}
    for bar in kline.bars:
        if bar.close <= 0:
            continue
        closes[_bar_date(bar)] = bar.close
    if not closes:
        return "", 0.0
    latest_date = max(closes)
    return latest_date, closes[latest_date]


async def quote_session_leads_kline(
    market: str,
    tickers: Set[str],
    stock_store: StockStore,
    kline_store: KlineStoreReader,
    *,
    now: Optional[datetime] = None,
) -> bool:
    """
    True when live quotes reflect a session after the latest stored daily kline.

    Heuristic: quote.pre_close ≈ last kline close → change_percent prices the next session.

    Requires the local regular session to have started so pre-market calendar
    rollovers (e.g. US still on prior close while CN is already trading) do not
    fabricate a next-day index point.
    """
    if not market_regular_session_has_started(market, now=now):
        return False
    session_date = market_local_date(market, now=now)
    if not _is_weekday(_parse_iso_date(session_date)):
        return False

    chunk_size = 50
    tickers_list = list(tickers)
    for i in range(0, len(tickers_list), chunk_size):
        chunk = tickers_list[i : i + chunk_size]
        batch = await kline_store.get_klines(chunk) if hasattr(kline_store, "get_klines") else None
        for ticker in chunk:
            market_code = stock_store.find_market(ticker)
            if market_code != market:
                continue
            stock = stock_store.get(market, ticker)
            quote = stock.stock_quote if stock else None
            if quote is None:
                continue
            kline_date, kline_close = _latest_kline_close(batch.items.get(ticker) if batch else None)
            if not kline_date or kline_close <= 0:
                continue
            if session_date <= kline_date:
                continue
            if not _is_plausible_live_session_date(session_date, kline_date):
                continue
            if _pre_close_matches_kline(quote.pre_close, kline_close):
                return True
    return False


async def market_cap_weighted_quote_session_return(
    market: str,
    tickers: Set[str],
    stock_store: StockStore,
    kline_store: KlineStoreReader,
) -> Optional[float]:
    """Market-cap weighted average of quote change_percent for the live session."""
    weighted_sum = 0.0
    weight_total = 0.0

    chunk_size = 500
    tickers_list = list(tickers)
    for i in range(0, len(tickers_list), chunk_size):
        chunk = tickers_list[i : i + chunk_size]
        batch = await kline_store.get_klines(chunk) if hasattr(kline_store, "get_klines") else None
        for ticker in chunk:
            if stock_store.find_market(ticker) != market:
                continue
            stock = stock_store.get(market, ticker)
            if stock is None or not stock_passes_sector_performance_weight(stock):
                continue
            quote = stock.stock_quote
            if quote is None:
                continue
            kline_date, kline_close = _latest_kline_close(batch.items.get(ticker) if batch else None)
            if not kline_date or not _pre_close_matches_kline(quote.pre_close, kline_close):
                continue
            contribution = market_cap_weighted_quote_change(
                change_percent=quote.change_percent,
                market_cap=quote.market_cap,
            )
            if contribution is None:
                continue
            weight, weighted_change = contribution
            weighted_sum += weighted_change
            weight_total += weight

    if weight_total <= 0:
        return None
    return weighted_sum / weight_total


async def append_quote_session_point(
    series: List[Tuple[str, float]],
    market: str,
    tickers: Set[str],
    stock_store: StockStore,
    kline_store: KlineStoreReader,
    *,
    now: Optional[datetime] = None,
) -> List[Tuple[str, float]]:
    """Extend the index with one live-quote point when quotes lead daily klines."""
    if not series or not tickers:
        return series
    if not await quote_session_leads_kline(market, tickers, stock_store, kline_store, now=now):
        return series

    session_date = market_local_date(market, now=now)
    kline_latest = max(day for day, _ in series)
    if session_date <= kline_latest:
        return series
    if not _is_plausible_live_session_date(session_date, kline_latest):
        return series

    session_return = await market_cap_weighted_quote_session_return(market, tickers, stock_store, kline_store)
    if session_return is None:
        return series

    last_level = series[-1][1]
    if last_level <= 0:
        return series

    next_level = round(last_level * (1 + session_return / 100.0), 4)
    if series[-1][0] == session_date:
        return series[:-1] + [(session_date, next_level)]
    return series + [(session_date, next_level)]


def _load_index_member(
    ticker: str,
    stock_store: StockStore,
    kline: StockKlineResponse | None,
) -> Optional[_IndexMember]:
    market = stock_store.find_market(ticker)
    if market is None:
        return None
    stock = stock_store.get(market, ticker)
    if stock is None or not stock_passes_sector_performance_weight(stock):
        return None
    weight = market_cap_weight(stock)
    if weight is None:
        return None
    if kline is None or not kline.bars:
        return None

    segment = latest_segment_ohlc(kline.bars)
    if segment is None:
        return None

    first_date = segment.first_date
    base_close = segment.closes[first_date]
    if base_close <= 0:
        return None

    return _IndexMember(
        weight=weight,
        closes=segment.closes,
        opens=segment.opens,
        first_date=first_date,
        first_open=segment.first_open,
        base_close=base_close,
        prev_closes=segment.prev_closes,
    )


async def compute_market_index_series(
    tickers: Set[str],
    stock_store: StockStore,
    kline_store: KlineStoreReader,
) -> List[Tuple[str, float]]:
    """
    Market-cap-weighted index on this market's own trading calendar.

    Each day:
      sector_return = Σ(weight_i × daily_return_i) / Σ(weight_i)
      index *= (1 + sector_return)

    Weights are market_cap from the current quote. Only the latest contiguous kline
    segment is used (ticker reuse after long gaps is ignored). Listing day uses
    close/open; later days use close-to-close within the segment. Names with a
    single-day gain above 50% are excluded from the daily cap-weighted average.
    """
    members: List[_IndexMember] = []
    chunk_size = 50
    tickers_list = list(tickers)
    for i in range(0, len(tickers_list), chunk_size):
        chunk = tickers_list[i : i + chunk_size]
        batch = await kline_store.get_klines(chunk) if hasattr(kline_store, "get_klines") else None
        for ticker in chunk:
            member = _load_index_member(
                ticker,
                stock_store,
                batch.items.get(ticker) if batch else None,
            )
            if member is not None:
                members.append(member)

    if not members:
        return []

    market_dates = sorted({day for member in members for day in member.closes})
    if not market_dates:
        return []

    index_level = INDEX_BASE
    points: List[Tuple[str, float]] = []

    for market_date in market_dates:
        weighted_return = 0.0
        weight_sum = 0.0

        for member in members:
            if market_date < member.first_date:
                continue
            close = member.closes.get(market_date)
            if close is None:
                continue

            daily_return = member_daily_return(
                date=market_date,
                close=close,
                first_date=member.first_date,
                prev_closes=member.prev_closes,
                opens=member.opens,
            )
            if daily_return is None:
                continue
            if not sector_member_daily_return_usable(daily_return):
                continue

            weighted_return += member.weight * daily_return
            weight_sum += member.weight

        if weight_sum > 0:
            index_level *= 1 + weighted_return / weight_sum
        points.append((market_date, round(index_level, 4)))

    return points
