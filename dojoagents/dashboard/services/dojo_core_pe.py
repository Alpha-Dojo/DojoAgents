from __future__ import annotations

import math
from typing import List, Optional

from dojoagents.dashboard.services.kline_store import KlineStore
from dojoagents.dashboard.services.fin_indicators_utils import (
    anchor_for_date,
    build_quarter_net_profit_map,
    build_ttm_schedule,
    prepare_single_quarter_rows,
    ttm_net_profit_for_anchor,
)
from dojoagents.dashboard.services.kline_bar_utils import DATA_START_DATE, extract_bar_time
from dojoagents.dashboard.services.stock_fin_indicators_store import StockFinIndicatorsStore
from dojoagents.dashboard.services.stock_store import MARKETS, StockStore
from dojoagents.dashboard.schemas.dojo_core import CorePeBandPoint, CoreTickerPeBandResponse


def resolve_total_shares(stock_store: StockStore, market: str, ticker: str) -> Optional[float]:
    stock = stock_store.get(market, ticker)
    if stock is None or stock.stock_quote is None:
        return None
    quote = stock.stock_quote
    if quote.total_shares > 0:
        return quote.total_shares
    if quote.last_price > 0 and quote.market_cap > 0:
        return quote.market_cap / quote.last_price
    return None


def _compute_band_stats(values: List[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    mean = sum(values) / len(values)
    if len(values) == 1:
        return mean, 0.0
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return mean, math.sqrt(variance)


def build_pe_band_points(
    *,
    bars: List[dict],
    fin_rows: List[dict],
    market: str,
    total_shares: float,
) -> List[CorePeBandPoint]:
    single_quarter_rows = prepare_single_quarter_rows(fin_rows, market)
    profit_by_quarter = build_quarter_net_profit_map(single_quarter_rows)
    schedule = build_ttm_schedule(single_quarter_rows)

    raw_points: List[tuple[str, float]] = []
    for row in bars:
        trade_date = extract_bar_time(row)
        close = row.get("close")
        if not trade_date or close is None:
            continue

        anchor = anchor_for_date(trade_date, schedule)
        if anchor is None:
            continue
        ttm_profit = ttm_net_profit_for_anchor(anchor[0], anchor[1], profit_by_quarter)
        if ttm_profit is None or ttm_profit <= 0:
            continue

        market_cap = float(close) * total_shares
        pe = market_cap / ttm_profit
        if not math.isfinite(pe) or pe <= 0:
            continue
        raw_points.append((trade_date, pe))

    mean, std = _compute_band_stats([pe for _, pe in raw_points])
    return [
        CorePeBandPoint(
            date=trade_date,
            pe=round(pe, 2),
            mean=round(mean, 2),
            upper1=round(mean + std, 2),
            lower1=round(mean - std, 2),
            upper2=round(mean + 2 * std, 2),
            lower2=round(mean - 2 * std, 2),
        )
        for trade_date, pe in raw_points
    ]


def _bar_rows_from_bars(bars: List) -> List[dict]:
    rows: List[dict] = []
    for bar in bars:
        if hasattr(bar, "bar_time"):
            trade_date = bar.bar_time
            close = bar.close
        else:
            row = bar if isinstance(bar, dict) else {}
            trade_date = row.get("bar_time") or row.get("datetime") or row.get("date")
            close = row.get("close")
        if not trade_date or close is None:
            continue
        rows.append({"bar_time": trade_date, "close": close})
    return rows


async def resolve_core_ticker_pe_band(
    ticker: str,
    *,
    market: Optional[str] = None,
    limit: int = 252,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    kline_t: str = "1D",
    stock_store: StockStore,
    kline_store: KlineStore,
    fin_indicators_store: StockFinIndicatorsStore,
    fin_rows: Optional[List[dict]] = None,
    bars: Optional[List] = None,
    as_of: Optional[str] = None,
) -> Optional[CoreTickerPeBandResponse]:
    symbol = ticker.strip()
    if not symbol:
        return None

    market_code = (market or stock_store.find_market(symbol) or "").lower()
    if market_code not in MARKETS or stock_store.get(market_code, symbol) is None:
        return None

    total_shares = resolve_total_shares(stock_store, market_code, symbol)
    if total_shares is None or total_shares <= 0:
        return None

    if bars is not None:
        bar_rows = _bar_rows_from_bars(bars)
        resolved_as_of = as_of
        if not bar_rows:
            return None
    else:
        kline_response = await kline_store.get_or_fetch_kline(
            symbol,
            market=market_code,
            kline_t=kline_t,
            start_time=start_time,
            end_time=end_time,
            min_bar_time=None if start_time else DATA_START_DATE,
            limit=limit if not start_time else None,
        )
        if kline_response is None or not kline_response.bars:
            return None
        bar_rows = _bar_rows_from_bars(kline_response.bars)
        resolved_as_of = kline_response.as_of
        if not bar_rows:
            return None

    fin_limit = max(24, min(50, limit // 10 + 8))
    if fin_rows is None:
        try:
            fin_response = await fin_indicators_store.get_for_ticker(
                symbol,
                market=market_code,
                limit=fin_limit,
            )
        except ValueError:
            return None
        fin_rows = fin_response.items

    if not fin_rows:
        return None

    points = build_pe_band_points(
        bars=bar_rows,
        fin_rows=fin_rows,
        market=market_code,
        total_shares=total_shares,
    )

    return CoreTickerPeBandResponse(
        ticker=symbol,
        market=market_code,
        as_of=resolved_as_of or "",
        total_shares=total_shares,
        points=points,
    )
