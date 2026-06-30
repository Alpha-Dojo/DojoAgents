from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from dojoagents.dashboard.services.kline_store import KlineStore
from dojoagents.dashboard.services.sector_constituents import MARKETS, SectorLevel, collect_sector_scope_tickers
from dojoagents.dashboard.services.sector_earnings_index import (
    compute_market_index_series,
    filter_cap_weighted_tickers,
)
from dojoagents.dashboard.services.precompute_sector_daily import DATA_START_DATE
from dojoagents.dashboard.services.sector_store import ResolvedSectorPath
from dojoagents.dashboard.services.stock_store import StockStore
from dojoagents.dashboard.services.sector_scope_performance_stats import compute_market_performance_stats
from dojoagents.dashboard.schemas.dojo_sphere import (
    SectorPerformanceMarketPoint,
    SectorPerformancePoint,
    SectorPerformanceResponse,
)

from dojoagents.logging import LOGGER

WINDOW_DAYS = 365  # legacy; performance window now anchors at DATA_START_DATE

# Backward-compatible test imports
_compute_market_index_series = compute_market_index_series


def _parse_date(value: str) -> date:
    return datetime.strptime(value[:10], "%Y-%m-%d").date()


def _latest_series_date(series: List[Tuple[str, float]]) -> str:
    if not series:
        return ""
    return max(day for day, _ in series)


def _resolve_unified_window_start(by_market: Dict[str, List[Tuple[str, float]]]) -> str:
    """Fixed inception at DATA_START_DATE (2025-01-01), matching Folio/Entity charts."""
    del by_market
    return DATA_START_DATE


def _resolve_market_window_bounds(
    series: List[Tuple[str, float]],
    *,
    unified_start: str,
) -> Tuple[str, str]:
    """Window from DATA_START_DATE through this market's latest trading day."""
    if not series or not unified_start:
        return "", ""
    end_d = _parse_date(_latest_series_date(series))
    start_d = _parse_date(unified_start)
    first_on_or_after = next((day for day, _ in series if day >= unified_start), "")
    if first_on_or_after:
        first_d = _parse_date(first_on_or_after)
        if first_d > start_d:
            start_d = first_d
    return start_d.isoformat(), end_d.isoformat()


def _resolve_window_bounds(by_market: Dict[str, List[Tuple[str, float]]]) -> Tuple[str, str]:
    """Coarse union window (unified start, max end) for merged cross-market series."""
    unified_start = _resolve_unified_window_start(by_market)
    if not unified_start:
        return "", ""
    ends = [_latest_series_date(by_market.get(market, [])) for market in MARKETS]
    ends = [day for day in ends if day]
    if not ends:
        return "", ""
    return unified_start, max(ends)


def _seed_market_values_before_window(
    lookup: Dict[str, Dict[str, float]],
    start_date: str,
) -> Dict[str, float]:
    """Carry the last pre-window index into the unified calendar for forward-fill."""
    seeded: Dict[str, float] = {}
    for market in MARKETS:
        last: Optional[float] = None
        for day, value in sorted(lookup.get(market, {}).items()):
            if day < start_date:
                last = value
            else:
                break
        if last is not None:
            seeded[market] = last
    return seeded


@dataclass(frozen=True)
class _MergedPerformance:
    points: List[SectorPerformancePoint]
    window_start: str
    window_end: str


def _merge_market_series(
    by_market: Dict[str, List[Tuple[str, float]]],
) -> _MergedPerformance:
    """Merge on union calendar; each market stops updating after its last trading day."""
    lookup: Dict[str, Dict[str, float]] = {market: dict(series) for market, series in by_market.items()}
    market_windows = {
        market: _resolve_market_window_bounds(
            by_market.get(market, []),
            unified_start=_resolve_unified_window_start(by_market),
        )
        for market in MARKETS
    }
    start_date, end_date = _resolve_window_bounds(by_market)
    if not start_date:
        return _MergedPerformance(points=[], window_start="", window_end="")

    dates = sorted(day for market in MARKETS for day, _ in by_market.get(market, []) if market_windows[market][0] <= day <= market_windows[market][1])
    if not dates:
        return _MergedPerformance(points=[], window_start=start_date, window_end=end_date)

    last_by_market = _seed_market_values_before_window(lookup, start_date)
    points: List[SectorPerformancePoint] = []
    for day in dates:
        point = SectorPerformancePoint(date=day)
        for market in MARKETS:
            window_start, window_end = market_windows[market]
            if not window_start or day > window_end:
                continue
            raw = lookup.get(market, {}).get(day)
            if raw is not None:
                last_by_market[market] = raw
            if market in last_by_market and day >= window_start:
                setattr(point, market, last_by_market[market])
        points.append(point)
    return _MergedPerformance(points=points, window_start=start_date, window_end=end_date)


def _clip_series_to_window(
    series: List[Tuple[str, float]],
    window_start: str,
    window_end: str,
) -> List[SectorPerformanceMarketPoint]:
    if not window_start or not window_end:
        return []
    return [SectorPerformanceMarketPoint(date=day, value=value) for day, value in series if window_start <= day <= window_end]


def _precomputed_scope_level_ids(path: ResolvedSectorPath, scope: SectorLevel) -> tuple[str, str]:
    level2_id = path.level2_id if scope in ("L2", "L3") else ""
    level3_id = path.level3_id if scope == "L3" else ""
    return level2_id, level3_id


def _market_series_from_precomputed(
    sector_precomputed_store: Any,
    path: ResolvedSectorPath,
    *,
    scope: SectorLevel,
    market: str,
) -> tuple[List[Tuple[str, float]], int]:
    """Read index curve and member count from ``sector_daily`` without live quote overlay."""
    level2_id, level3_id = _precomputed_scope_level_ids(path, scope)
    daily_rows = sector_precomputed_store.get_sector_daily(
        scope=scope,
        level1_id=path.level1_id,
        level2_id=level2_id,
        level3_id=level3_id,
        market=market,
    )
    if not daily_rows:
        return [], 0
    sorted_rows = sorted(daily_rows, key=lambda row: str(row.get("trade_date") or ""))
    series = [
        (str(row["trade_date"]), float(row["index_level"]))
        for row in sorted_rows
        if str(row.get("trade_date") or "") >= DATA_START_DATE
    ]
    member_count = int(sorted_rows[-1].get("member_count") or 0)
    return series, member_count


async def _extend_series_with_live_klines(
    series: List[Tuple[str, float]],
    *,
    market: str,
    tickers: set[str],
    stock_store: StockStore,
    kline_store: KlineStore,
) -> List[Tuple[str, float]]:
    """Append live kline-derived index levels after the last precomputed trade date."""
    if not series or not tickers:
        return series

    eligible = filter_cap_weighted_tickers(market, set(tickers), stock_store)
    if not eligible:
        return series

    live = await compute_market_index_series(eligible, stock_store, kline_store)
    if not live:
        return series

    last_date, last_level = series[-1]
    anchor_value: float | None = None
    for day, value in reversed(live):
        if day <= last_date:
            anchor_value = value
            break
    if anchor_value is None or anchor_value <= 0 or last_level <= 0:
        return series

    scale = last_level / anchor_value
    existing = {day for day, _ in series}
    merged = list(series)
    for day, value in live:
        if day <= last_date or day in existing:
            continue
        merged.append((day, round(value * scale, 4)))
    merged.sort(key=lambda item: item[0])
    return merged


async def resolve_scope_unified_window_start(
    stock_store: StockStore,
    kline_store: KlineStore,
    sector_precomputed_store: Any,
    path: ResolvedSectorPath,
    *,
    scope: SectorLevel = "L3",
) -> str:
    """Unified performance window start (DATA_START_DATE)."""
    del stock_store, kline_store
    by_market: Dict[str, List[Tuple[str, float]]] = {}
    for market in MARKETS:
        series, _member_count = _market_series_from_precomputed(
            sector_precomputed_store,
            path,
            scope=scope,
            market=market,
        )
        by_market[market] = series
    return _resolve_unified_window_start(by_market)


async def compute_sector_scope_performance(
    stock_store: StockStore,
    kline_store: KlineStore,
    sector_precomputed_store: Any,
    path: ResolvedSectorPath,
    *,
    scope: SectorLevel = "L3",
) -> SectorPerformanceResponse:
    """Cross-market market-cap-weighted sector index curves for the selected scope."""
    if scope not in ("L1", "L2", "L3"):
        scope = "L3"

    scope_tickers = collect_sector_scope_tickers(sector_precomputed_store, path)
    by_market: Dict[str, List[Tuple[str, float]]] = {}
    members_by_market: Dict[str, int] = {}

    for market in MARKETS:
        series, member_count = _market_series_from_precomputed(
            sector_precomputed_store,
            path,
            scope=scope,
            market=market,
        )
        try:
            series = await _extend_series_with_live_klines(
                series,
                market=market,
                tickers=scope_tickers.get(scope) or set(),
                stock_store=stock_store,
                kline_store=kline_store,
            )
        except Exception:
            LOGGER.exception(
                "Live sector performance tail extension failed for %s/%s scope=%s",
                path.level1_id,
                path.level3_id,
                scope,
            )
        by_market[market] = series
        members_by_market[market] = member_count

    merged = _merge_market_series(by_market)

    windows_by_market = {
        market: _resolve_market_window_bounds(
            by_market.get(market, []),
            unified_start=_resolve_unified_window_start(by_market),
        )
        for market in MARKETS
    }
    series_by_market = {
        market: _clip_series_to_window(
            by_market.get(market, []),
            windows_by_market[market][0],
            windows_by_market[market][1],
        )
        for market in MARKETS
    }
    stats_by_market = {}
    for market in MARKETS:
        window_start, window_end = windows_by_market[market]
        stats = compute_market_performance_stats(
            by_market.get(market, []),
            window_start,
            window_end,
        )
        if stats is not None:
            stats_by_market[market] = stats

    return SectorPerformanceResponse(
        level1_id=path.level1_id,
        level2_id=path.level2_id,
        level3_id=path.level3_id,
        scope=scope,
        window_start=merged.window_start or None,
        window_end=merged.window_end or None,
        points=merged.points,
        series_by_market=series_by_market,
        stats_by_market=stats_by_market,
        members_by_market=members_by_market,
    )
