from __future__ import annotations
import asyncio
from types import SimpleNamespace
from typing import Any, Optional
from datetime import date
from dojoagents.dashboard.schemas.benchmark import DojoMeshBenchmarksResponse
from dojoagents.dashboard.schemas.dojo_core import CoreTickerPeBandResponse
from dojoagents.dashboard.schemas.dojo_mesh import BilingualText
from dojoagents.dashboard.schemas.domain_api import (
    BenchmarkKlinePoint,
    BenchmarkSnapshot,
    CompanyTickerSearchResponse,
    MarketOverviewResponse,
    MarketSectorMovers,
    MarketStatsSnapshot,
    PortfolioHoldingRow,
    PortfolioKpi,
    PeBandPoint,
    PortfolioAnalysisResponseV1,
    PortfolioListResponseV1,
    PortfolioSummaryItem,
    SectorAnalysisResponse,
    SectorAnalysisScope,
    SectorConstituentsResponseV1,
    SectorMoverItem,
    SectorMoverMember,
    SectorMoversResponse,
    SectorPerformancePoint,
    SectorPerformanceStats,
    SectorScopePerformance,
    StockScreenItem,
    StockScreenResponse,
    TickerEventItem,
    TickerFinancialsResponseV1,
    TickerNewsItem,
    TickerNewsEventsResponseV1,
    TickerPriceTrendsResponseV1,
    TickerQuoteResponseV1,
    TickerSectorPath,
    IncomeDistributionSlice,
)
from dojoagents.dashboard.schemas.portfolio import (
    PortfolioCapitalConfig,
    UpdatePortfolioRequest,
)
from dojoagents.dashboard.services.dojo_core_pe import resolve_core_ticker_pe_band
from dojoagents.dashboard.services.dojo_core_quote import resolve_core_ticker_quote
from dojoagents.dashboard.services.dojo_core_search import search_core_tickers
from dojoagents.dashboard.services.dojo_core_sector import resolve_core_ticker_sector
from dojoagents.dashboard.services.domain_utils import (
    filter_date_rows,
    normalize_market_code,
    to_native_market_code,
)
from dojoagents.dashboard.services.fin_indicators_utils import report_type_for_market
from dojoagents.dashboard.services.market_sector_lead import (
    MAX_SECTOR_MEMBERS,
    _stock_bilingual_name,
    concept_code_for,
)
from dojoagents.dashboard.services.market_stats import compute_market_stats
from dojoagents.dashboard.services.portfolio_service import DEFAULT_BENCHMARKS
from dojoagents.dashboard.services.sector_constituents import MARKETS
from dojoagents.dashboard.services.sector_constituents_list import list_sector_constituents
from dojoagents.dashboard.services.sector_scope_performance import (
    compute_sector_scope_performance,
)
from dojoagents.dashboard.services.sector_scope_stats import compute_sector_scope_metrics


def _sector_scope_cache_key(level1_id: str, level2_id: str, level3_id: str, scope: str) -> str:
    return f"{scope}/{level1_id}/{level2_id}/{level3_id}"


def _normalize_native_market(market: Optional[str]) -> Optional[str]:
    normalized = normalize_market_code(market)
    return to_native_market_code(normalized)


def _model_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return dict(value)
    return dict(getattr(value, "__dict__", {}) or {})


def _stats_snapshot(stats: Any, *, market: Optional[str] = None) -> MarketStatsSnapshot:
    data = _model_dict(stats)
    raw_market = market or data.get("market")
    return MarketStatsSnapshot(
        market=to_native_market_code(raw_market) or str(raw_market or ""),
        listed_count=int(data.get("listed_count") or 0),
        total_market_cap=float(data.get("total_market_cap") or 0.0),
        weighted_pe=data.get("weighted_pe"),
        simple_pe=data.get("simple_pe"),
        pe_sample_count=int(data.get("pe_sample_count") or 0),
    )


def _benchmark_snapshot(benchmark: Any) -> BenchmarkSnapshot:
    data = _model_dict(benchmark)
    bars = list(data.get("kline") or [])
    dates = [str((_model_dict(bar).get("datetime") or _model_dict(bar).get("date") or "")).strip() for bar in bars]
    dates = [item for item in dates if item]
    return BenchmarkSnapshot(
        market=to_native_market_code(data.get("market")) or str(data.get("market") or ""),
        symbol=str(data.get("symbol") or ""),
        name=BilingualText.model_validate(data.get("name") or {}),
        price=float(data.get("price") or 0.0),
        change_percent=float(data.get("change_percent") or 0.0),
        window_start=data.get("window_start") or (dates[0] if dates else None),
        window_end=data.get("window_end") or (dates[-1] if dates else None),
        kline=[
            BenchmarkKlinePoint(
                datetime=str(_model_dict(bar).get("datetime") or _model_dict(bar).get("date") or ""),
                close=float(_model_dict(bar).get("close") or 0.0),
            )
            for bar in bars
        ],
    )


def _sector_member(member: Any) -> SectorMoverMember:
    data = _model_dict(member)
    return SectorMoverMember(
        ticker=str(data.get("ticker") or ""),
        name=BilingualText.model_validate(data.get("name") or {}),
        last_price=float(data.get("last_price") or 0.0),
        market_cap=float(data.get("market_cap") or 0.0),
        change_percent=float(data.get("change_percent") or 0.0),
    )


def _sector_mover_item(item: Any) -> SectorMoverItem:
    data = _model_dict(item)
    members = list(data.get("top_members") or data.get("members") or [])
    member_count = int(data.get("member_count") or len(members))
    avg_market_cap = float(data.get("avg_market_cap") or 0.0)
    total_market_cap = float(data.get("total_market_cap") or 0.0)
    if total_market_cap == 0.0 and avg_market_cap and member_count:
        total_market_cap = avg_market_cap * member_count
    return SectorMoverItem(
        level1_id=str(data.get("level1_id") or ""),
        level2_id=str(data.get("level2_id") or ""),
        level3_id=str(data.get("level3_id") or ""),
        concept_code=str(data.get("concept_code") or ""),
        name=BilingualText.model_validate(data.get("name") or {}),
        change_percent=float(data.get("change_percent") or 0.0),
        avg_market_cap=avg_market_cap,
        total_market_cap=total_market_cap,
        member_count=member_count,
        sample_tickers=list(data.get("sample_tickers") or []),
        top_members=[_sector_member(member) for member in members],
    )


def _performance_points(rows: Any) -> list[SectorPerformancePoint]:
    points: list[SectorPerformancePoint] = []
    for row in rows or []:
        data = _model_dict(row)
        date_value = data.get("date") or data.get("datetime")
        value = data.get("value")
        if date_value is None or value is None:
            continue
        points.append(SectorPerformancePoint(date=str(date_value), value=float(value)))
    return points


def _risk_stats(value: Any) -> SectorPerformanceStats:
    data = _model_dict(value)
    return SectorPerformanceStats(
        cumulative_return_pct=data.get("cumulative_return_pct"),
        sharpe_ratio=data.get("sharpe_ratio"),
        max_drawdown_pct=data.get("max_drawdown_pct"),
        calmar_ratio=data.get("calmar_ratio"),
        volatility_pct=data.get("volatility_pct"),
        trading_days=int(data.get("trading_days") or 0),
    )


def _portfolio_summary_item(item: Any) -> PortfolioSummaryItem:
    data = _model_dict(item)
    return PortfolioSummaryItem(
        id=str(data.get("id") or ""),
        name=str(data.get("name") or ""),
        subtitle=data.get("subtitle"),
        kind=data.get("kind") or "manual",
        pinned=bool(data.get("pinned", False)),
        today_change=data.get("today_change"),
        net_value_usd=data.get("net_value_usd"),
    )


def _safe_stock_bilingual_name(stock: Any, fallback: str) -> BilingualText:
    if stock is None:
        return BilingualText(zh=fallback, en=fallback)
    try:
        return _stock_bilingual_name(stock)
    except AttributeError:
        zh = getattr(stock, "short_name", None) or getattr(stock, "name", None) or getattr(stock, "ticker", None) or fallback
        en = getattr(stock, "long_name", None) or zh
        return BilingualText(zh=str(zh), en=str(en))


def _sector_option_to_path(option: Any) -> TickerSectorPath:
    data = _model_dict(option)
    label = _model_dict(data.get("label") or {})
    labels = {
        "L1": BilingualText.model_validate(label.get("level_1") or {}),
        "L2": BilingualText.model_validate(label.get("level_2") or {}),
        "L3": BilingualText.model_validate(label.get("level_3") or {}),
    }
    return TickerSectorPath(
        role=data.get("role") or "primary",
        level1_id=str(data.get("level1_id") or ""),
        level2_id=str(data.get("level2_id") or ""),
        level3_id=str(data.get("level3_id") or ""),
        labels=labels,
    )


def _income_dimension(mainop_type: Any) -> str:
    return {"1": "industry", "2": "product", "3": "region"}.get(str(mainop_type or ""), "product")


def _date_bounds(rows: list[Any], *keys: str) -> tuple[Optional[str], Optional[str]]:
    dates: list[str] = []
    for row in rows:
        data = _model_dict(row)
        for key in keys:
            raw = data.get(key)
            if raw:
                dates.append(str(raw)[:10])
                break
    if not dates:
        return None, None
    return min(dates), max(dates)


def _holding_row(item: Any) -> PortfolioHoldingRow:
    data = _model_dict(item)
    return PortfolioHoldingRow(
        ticker=str(data.get("ticker") or ""),
        name=str(data.get("name") or data.get("ticker") or ""),
        name_zh=str(data.get("name_zh") or ""),
        name_en=str(data.get("name_en") or ""),
        market=to_native_market_code(data.get("market")) or str(data.get("market") or ""),
        shares=float(data.get("shares") or 0.0),
        weight=float(data.get("weight") or 0.0),
        cost=float(data.get("cost") or 0.0),
        cost_low=data.get("cost_low"),
        cost_high=data.get("cost_high"),
        uses_default_cost=bool(data.get("uses_default_cost", True)),
        cost_date=data.get("cost_date"),
        open_date=data.get("open_date"),
        uses_default_open_date=bool(data.get("uses_default_open_date", True)),
        cost_basis=float(data.get("cost_basis") or 0.0),
        price=float(data.get("price") or 0.0),
        change_percent=float(data.get("change_percent") or 0.0),
        total_return_pct=data.get("total_return_pct"),
        market_value=float(data.get("market_value") or 0.0),
        sector_l1=str(data.get("sector_l1") or ""),
        sector_l2=str(data.get("sector_l2") or ""),
        sector_l3=str(data.get("sector_l3") or ""),
    )


def _portfolio_kpi(item: Any) -> PortfolioKpi:
    data = _model_dict(item)
    return PortfolioKpi(
        key=data.get("key") or "netValue",
        value=str(data.get("value") or ""),
        delta=data.get("delta"),
        delta_tone=data.get("delta_tone"),
    )


def _market_performance_points(dates: list[str], values: list[Any]) -> list[SectorPerformancePoint]:
    points = []
    for index, value in enumerate(values):
        if index >= len(dates):
            break
        points.append(SectorPerformancePoint(date=str(dates[index]), value=float(value or 0.0)))
    return points


def _portfolio_analysis(detail: Any) -> PortfolioAnalysisResponseV1:
    data = _model_dict(detail)
    config = _model_dict(data.get("config") or {})
    performance = _model_dict(data.get("performance") or {})
    dates = list(performance.get("dates") or [])
    nav_by_market: dict[str, list[SectorPerformancePoint]] = {}
    benchmark_by_market: dict[str, list[SectorPerformancePoint]] = {}
    stats_by_market: dict[str, SectorPerformanceStats] = {}
    benchmark_symbol_by_market = {to_native_market_code(market) or market: str(symbol) for market, symbol in (performance.get("benchmark_symbol_by_market") or {}).items()}
    for market, series in (performance.get("series_by_market") or {}).items():
        series_data = _model_dict(series)
        market_key = to_native_market_code(market) or market
        market_dates = list(series_data.get("dates") or dates)
        nav_by_market[market_key] = _market_performance_points(market_dates, list(series_data.get("portfolio") or []))
        benchmark_by_market[market_key] = _market_performance_points(market_dates, list(series_data.get("benchmark") or []))
        stats_by_market[market_key] = _risk_stats(series_data.get("stats") or {})
        if series_data.get("benchmark_symbol"):
            benchmark_symbol_by_market[market_key] = str(series_data["benchmark_symbol"])
    if not nav_by_market and dates:
        nav_by_market["all"] = _market_performance_points(dates, list(performance.get("portfolio") or []))
        benchmark_by_market["all"] = _market_performance_points(dates, list(performance.get("benchmark") or []))
    return PortfolioAnalysisResponseV1(
        id=str(data.get("id") or ""),
        name=str(data.get("name") or ""),
        subtitle=data.get("subtitle"),
        benchmark=data.get("benchmark"),
        start_date=config.get("start_date"),
        capital_by_market={to_native_market_code(market) or market: float(value or 0.0) for market, value in (config.get("capital_by_market") or {}).items()},
        holdings=[_holding_row(item) for item in data.get("holdings") or []],
        kpis=[_portfolio_kpi(item) for item in data.get("kpis") or []],
        performance_window_start=performance.get("window_start"),
        performance_window_end=performance.get("window_end"),
        nav_by_market=nav_by_market,
        benchmark_by_market=benchmark_by_market,
        benchmark_symbol_by_market=benchmark_symbol_by_market,
        stats_by_market=stats_by_market,
        net_value_by_market={to_native_market_code(market) or market: float(value or 0.0) for market, value in (data.get("net_value_by_market") or {}).items()},
        cost_basis_by_market={to_native_market_code(market) or market: float(value or 0.0) for market, value in (data.get("cost_basis_by_market") or {}).items()},
    )


def portfolio_detail_to_analysis(detail: Any) -> PortfolioAnalysisResponseV1:
    return _portfolio_analysis(detail)


def _precomputed_market_candidates(market: Optional[str]) -> list[Optional[str]]:
    native_market = to_native_market_code(market) if market else None
    internal_market = normalize_market_code(market) if market else None
    candidates: list[Optional[str]] = []
    for candidate in (native_market, internal_market, market):
        if candidate not in candidates:
            candidates.append(candidate)
    return candidates or [None]


def _fallback_precomputed_sector_path(
    registry: Any,
    *,
    level1_id: str,
    level2_id: str,
    level3_id: str,
    market: Optional[str],
) -> Any | None:
    precomputed = getattr(registry, "sector_precomputed_store", None)
    getter = getattr(precomputed, "get_sector_constituents", None)
    if not callable(getter):
        return None
    for market_candidate in _precomputed_market_candidates(market):
        try:
            rows = getter(
                level1_id=level1_id,
                level2_id=level2_id,
                level3_id=level3_id,
                market=market_candidate,
            )
        except TypeError:
            rows = getter(level1_id, level2_id, level3_id, market=market_candidate)
        if rows:
            return SimpleNamespace(
                level1_id=level1_id,
                level2_id=level2_id,
                level3_id=level3_id,
                level1_zh="",
                level1_en="",
                level2_zh="",
                level2_en="",
                level3_zh="",
                level3_en="",
            )
    return None


def resolve_sector_analysis_path(
    registry: Any,
    *,
    level1_id: str,
    level2_id: str,
    level3_id: str,
) -> Any | None:
    path = registry.sector_store.find_resolved_path(level1_id, level2_id, level3_id)
    if path is not None:
        return path
    return _fallback_precomputed_sector_path(
        registry,
        level1_id=level1_id,
        level2_id=level2_id,
        level3_id=level3_id,
        market=None,
    )


async def search_company_ticker(
    registry,
    *,
    q: str,
    market: Optional[str],
    limit: int,
) -> CompanyTickerSearchResponse:
    internal_market = normalize_market_code(market)
    items = search_core_tickers(
        registry.stock_store,
        getattr(registry, "sector_precomputed_store", registry.stock_sector_store),
        registry.sector_store,
        q,
        market=internal_market,
        limit=limit,
    )
    mapped = [_model_dict(item) | {"market": _normalize_native_market(item.market) or item.market} for item in items]
    return CompanyTickerSearchResponse(query=q.strip(), items=mapped)


def build_taxonomy_tree(registry) -> dict[str, Any]:
    document = registry.sector_store.to_taxonomy_document()
    data = document.model_dump(mode="json") if hasattr(document, "model_dump") else dict(document or {})
    return {
        "version": data.get("version") or "api",
        "id_scheme": data.get("id_scheme") or "sector_id",
        "tree": [
            {
                "level1_id": level1.get("level1_id") or level1.get("id") or "",
                "name": level1.get("name") or {},
                "description": level1.get("description"),
                "children": [
                    {
                        "level2_id": level2.get("level2_id") or level2.get("id") or "",
                        "name": level2.get("name") or {},
                        "description": level2.get("description"),
                        "children": [
                            {
                                "level3_id": level3.get("level3_id") or level3.get("id") or "",
                                "name": level3.get("name") or {},
                                "definition": level3.get("definition"),
                            }
                            for level3 in level2.get("level_3", [])
                        ],
                    }
                    for level2 in level1.get("level_2", [])
                ],
            }
            for level1 in data.get("level_1", [])
        ],
    }


async def build_market_overview(
    registry,
    *,
    days: int,
    market: Optional[str],
) -> MarketOverviewResponse:
    benchmarks: DojoMeshBenchmarksResponse = await registry.benchmark_store.get_benchmarks(days=days)
    markets: dict[str, MarketStatsSnapshot] = {}
    benchmark_map: dict[str, list[BenchmarkSnapshot]] = {}
    requested_markets = [normalize_market_code(market)] if market else list(MARKETS)
    window_start = None
    window_end = None
    for internal_market in requested_markets:
        if internal_market is None:
            continue
        stats = compute_market_stats(
            to_native_market_code(internal_market) or internal_market,
            registry.stock_store.list_market(internal_market),
        )
        benchmark_payload = benchmarks.markets.get(internal_market) if benchmarks.markets else None
        benchmark_list: list[BenchmarkSnapshot] = []
        if benchmark_payload is not None:
            benchmark_list = [_benchmark_snapshot(item) for item in benchmark_payload.benchmarks]
            for benchmark in benchmark_payload.benchmarks:
                bars = benchmark.kline or []
                if bars:
                    dates = [getattr(bar, "date", None) or getattr(bar, "datetime", None) for bar in bars if getattr(bar, "date", None) or getattr(bar, "datetime", None)]
                    if dates:
                        start = dates[0]
                        end = dates[-1]
                        window_start = start if window_start is None else min(window_start, start)
                        window_end = end if window_end is None else max(window_end, end)
        native_market = to_native_market_code(internal_market) or internal_market
        markets[native_market] = _stats_snapshot(stats, market=native_market)
        benchmark_map[native_market] = benchmark_list
    return MarketOverviewResponse(
        days=days,
        window_start=window_start,
        window_end=window_end,
        as_of=benchmarks.as_of or window_end,
        markets=markets,
        benchmarks=benchmark_map,
    )


async def build_sector_movers(
    registry,
    *,
    days: int,
    limit: int,
    market: Optional[str],
    min_cap_by_market: Optional[dict[str, float]] = None,
) -> SectorMoversResponse:
    service = getattr(registry, "sector_movers_service", None)
    if service is not None:
        return await asyncio.to_thread(
            service.build_market_movers_response,
            days=days,
            limit=limit,
            market=market,
            min_cap_by_market=min_cap_by_market,
        )
    return await asyncio.to_thread(
        _build_sector_movers_fallback_sync,
        registry,
        days,
        limit,
        market,
        min_cap_by_market,
    )


async def build_stock_screen(
    registry,
    *,
    market: Optional[str],
    days: int,
    min_market_cap: Optional[float],
    max_market_cap: Optional[float],
    min_return_pct: Optional[float],
    max_return_pct: Optional[float],
    min_pe: Optional[float],
    max_pe: Optional[float],
    min_change_percent: Optional[float],
    max_change_percent: Optional[float],
    sort_by: str,
    sort_order: str,
    limit: int,
) -> StockScreenResponse:
    requested_markets = [normalize_market_code(market)] if market else list(MARKETS)
    rows: list[StockScreenItem] = []
    universe_count = 0
    as_of = None
    for internal_market in requested_markets:
        if internal_market is None:
            continue
        list_market = getattr(registry.stock_store, "list_market", None)
        stocks = list_market(internal_market) if callable(list_market) else []
        for stock in stocks:
            quote = getattr(stock, "stock_quote", None)
            if quote is None:
                continue
            universe_count += 1
            market_cap = getattr(quote, "market_cap", None)
            pe = getattr(quote, "pe", None)
            change_percent = getattr(quote, "change_percent", None)
            window_change_percent = None
            if min_market_cap is not None and (market_cap is None or market_cap < min_market_cap):
                continue
            if max_market_cap is not None and market_cap is not None and market_cap > max_market_cap:
                continue
            if min_pe is not None and (pe is None or pe < min_pe):
                continue
            if max_pe is not None and pe is not None and pe > max_pe:
                continue
            if min_change_percent is not None and (change_percent is None or change_percent < min_change_percent):
                continue
            if max_change_percent is not None and change_percent is not None and change_percent > max_change_percent:
                continue
            if min_return_pct is not None and (window_change_percent is None or window_change_percent < min_return_pct):
                continue
            if max_return_pct is not None and window_change_percent is not None and window_change_percent > max_return_pct:
                continue
            rows.append(
                StockScreenItem(
                    ticker=str(getattr(stock, "ticker", "")),
                    market=to_native_market_code(internal_market) or internal_market,
                    name=_safe_stock_bilingual_name(stock, str(getattr(stock, "ticker", ""))),
                    last_price=getattr(quote, "last_price", None),
                    change_percent=change_percent,
                    window_change_percent=window_change_percent,
                    market_cap=market_cap,
                    pe=pe,
                    pb=getattr(quote, "pb", None),
                )
            )
    sort_key = {
        "market_cap": lambda item: item.market_cap if item.market_cap is not None else float("-inf"),
        "return_pct": lambda item: item.window_change_percent if item.window_change_percent is not None else float("-inf"),
        "change_percent": lambda item: item.change_percent if item.change_percent is not None else float("-inf"),
        "pe": lambda item: item.pe if item.pe is not None else float("-inf"),
    }.get(sort_by, lambda item: item.market_cap if item.market_cap is not None else float("-inf"))
    rows = sorted(rows, key=sort_key, reverse=sort_order == "desc")
    return StockScreenResponse(
        days=days,
        market=to_native_market_code(market) if market else None,
        as_of=as_of,
        universe_count=universe_count,
        match_count=len(rows),
        items=rows[:limit],
    )


def _build_sector_movers_fallback_sync(
    registry,
    days: int,
    limit: int,
    market: Optional[str],
    min_cap_by_market: Optional[dict[str, float]] = None,
) -> SectorMoversResponse:
    min_cap_by_market = min_cap_by_market or {}
    requested_markets = [normalize_market_code(market)] if market else list(MARKETS)
    payload: dict[str, MarketSectorMovers] = {}

    sector_movers = registry.sector_precomputed_store.get_sector_movers_by_window(days)

    for internal_market in requested_markets:
        if internal_market is None:
            continue

        threshold = float(min_cap_by_market.get(internal_market) or 0.0)
        market_sectors = [s for s in sector_movers if s["market"] == internal_market and s["scope"] == "L3"]

        items: list[SectorMoverItem] = []
        for s in market_sectors:
            total_market_cap = s.get("total_market_cap", 0)
            if threshold > 0 and total_market_cap < threshold:
                continue

            # Fetch components using get_sector_constituents
            constituents = registry.sector_precomputed_store.get_sector_constituents(
                level1_id=s["level1_id"],
                level2_id=s["level2_id"],
                level3_id=s["level3_id"],
                market=internal_market,
            )

            # Fetch members returns
            tickers = [c["ticker"] for c in constituents]
            ticker_returns = registry.sector_precomputed_store.get_ticker_daily_by_window(days, tickers)
            ticker_return_map = {tr["ticker"]: tr["daily_return_pct"] for tr in ticker_returns}

            members = []
            for c in constituents:
                stock = registry.stock_store.get(internal_market, c["ticker"])
                if not stock:
                    continue
                change = ticker_return_map.get(c["ticker"], 0.0)
                members.append(
                    {
                        "ticker": c["ticker"],
                        "name": {"zh": stock.short_name or stock.ticker, "en": stock.long_name or stock.ticker},
                        "last_price": stock.stock_quote.last_price if stock.stock_quote else 0.0,
                        "market_cap": c.get("market_cap", 0.0) or 0.0,
                        "change_percent": round(change, 2),
                    }
                )

            sorted_members = sorted(members, key=lambda item: item["change_percent"], reverse=True)
            top_by_abs = sorted(members, key=lambda item: abs(item["change_percent"]), reverse=True)[:3]

            path = registry.sector_store.find_resolved_path(
                s["level1_id"],
                s["level2_id"],
                s["level3_id"],
            )
            if path is None:
                continue

            item = SectorMoverItem(
                level1_id=str(s["level1_id"]),
                level2_id=str(s["level2_id"]),
                level3_id=str(s["level3_id"]),
                concept_code=concept_code_for(internal_market, path.level3_zh, path.level3_en, "L3"),
                name=BilingualText(zh=path.level3_zh, en=path.level3_en),
                change_percent=round(s.get("daily_return_pct", 0), 2),
                avg_market_cap=(total_market_cap / s.get("member_count", 1)) if s.get("member_count") else 0.0,
                total_market_cap=float(total_market_cap or 0.0),
                sample_tickers=[m["ticker"] for m in top_by_abs],
                member_count=s.get("member_count", 0),
                top_members=[_sector_member(member) for member in sorted_members[:MAX_SECTOR_MEMBERS]],
            )
            items.append(item)

        gainers = sorted([item for item in items if item.change_percent > 0], key=lambda row: row.change_percent, reverse=True)[:limit]
        losers = sorted([item for item in items if item.change_percent < 0], key=lambda row: row.change_percent)[:limit]
        native_market = to_native_market_code(internal_market) or internal_market
        payload[native_market] = MarketSectorMovers(
            gainers=gainers,
            losers=losers,
        )
    return SectorMoversResponse(days=days, markets=payload)


async def build_sector_analysis(
    registry,
    path,
    *,
    scope: str,
) -> SectorAnalysisResponse:
    level1_id = str(path.level1_id)
    level2_id = str(path.level2_id)
    level3_id = str(path.level3_id)

    async def compute_metrics_payload() -> dict[str, Any]:
        result = await compute_sector_scope_metrics(
            registry.stock_store,
            registry.sector_precomputed_store,
            path,
        )
        return result.model_dump()

    if getattr(registry, "kline_store", None) is not None and getattr(registry.kline_store, "sector_precomputed_store", None) is None:
        registry.kline_store.sector_precomputed_store = registry.sector_precomputed_store
    metrics = await registry.dojo_sphere_service.metrics(
        f"{level1_id}/{level2_id}/{level3_id}",
        compute_metrics_payload,
    )
    scopes = {}
    sources: set[str] = set()
    stale = False
    for current_scope in ("L1", "L2", "L3"):

        async def compute_performance_payload(current_scope: str = current_scope) -> dict[str, Any]:
            result = await compute_sector_scope_performance(
                registry.stock_store,
                registry.kline_store,
                registry.sector_precomputed_store,
                path,
                scope=current_scope,
            )
            return result.model_dump()

        cached_performance = await registry.dojo_sphere_service.performance(
            _sector_scope_cache_key(level1_id, level2_id, level3_id, current_scope),
            compute_performance_payload,
        )
        performance = cached_performance.get("payload", cached_performance)
        scopes[current_scope] = SectorAnalysisScope(
            scope=current_scope,
            metrics=metrics,
            performance=performance,
        )
        if isinstance(cached_performance, dict) and cached_performance.get("source"):
            sources.add(cached_performance["source"])
        if isinstance(cached_performance, dict):
            stale = stale or bool(cached_performance.get("stale"))
    selected = scopes.get(scope) or scopes["L3"]
    selected_performance = selected.performance or {}
    selected_metrics = selected.metrics or {}
    raw_metrics_by_scope = selected_metrics.get("scopes") or {}
    metrics_by_scope = {}
    for scope_key, market_values in raw_metrics_by_scope.items():
        if not isinstance(market_values, dict):
            continue
        metrics_by_scope[scope_key] = {
            to_native_market_code(market_key)
            or market_key: {
                **_model_dict(metric),
                "market": to_native_market_code(_model_dict(metric).get("market") or market_key) or market_key,
            }
            for market_key, metric in market_values.items()
        }
    performance_by_scope = {}
    for scope_key, scope_payload in scopes.items():
        perf = scope_payload.performance or {}
        performance_by_scope[scope_key] = SectorScopePerformance(
            performance_window_start=perf.get("window_start") or perf.get("performance_window_start"),
            performance_window_end=perf.get("window_end") or perf.get("performance_window_end"),
            performance_by_market={
                to_native_market_code(market_key) or market_key: _performance_points(points)
                for market_key, points in (perf.get("series_by_market") or perf.get("performance_by_market") or {}).items()
            },
            stats_by_market={to_native_market_code(market_key) or market_key: _risk_stats(stats) for market_key, stats in (perf.get("stats_by_market") or {}).items()},
            members_by_market={to_native_market_code(market_key) or market_key: int(count or 0) for market_key, count in (perf.get("members_by_market") or {}).items()},
        )
    return SectorAnalysisResponse(
        level1_id=level1_id,
        level2_id=level2_id,
        level3_id=level3_id,
        scope=selected.scope,
        metrics_by_scope=metrics_by_scope,
        performance_window_start=selected_performance.get("window_start") or selected_performance.get("performance_window_start"),
        performance_window_end=selected_performance.get("window_end") or selected_performance.get("performance_window_end"),
        performance_by_market={
            to_native_market_code(market_key) or market_key: _performance_points(points)
            for market_key, points in (selected_performance.get("series_by_market") or selected_performance.get("performance_by_market") or {}).items()
        },
        stats_by_market={to_native_market_code(market_key) or market_key: _risk_stats(stats) for market_key, stats in (selected_performance.get("stats_by_market") or {}).items()},
        members_by_market={to_native_market_code(market_key) or market_key: int(count or 0) for market_key, count in (selected_performance.get("members_by_market") or {}).items()},
        performance_by_scope=performance_by_scope,
        scopes=scopes,
    )


async def build_sector_constituents_v1(
    registry,
    *,
    level1_id: str,
    level2_id: str,
    level3_id: str,
    scope: str,
    market: Optional[str],
    days: int,
) -> SectorConstituentsResponseV1:
    path = registry.sector_store.find_resolved_path(level1_id, level2_id, level3_id)
    if path is None:
        path = _fallback_precomputed_sector_path(
            registry,
            level1_id=level1_id,
            level2_id=level2_id,
            level3_id=level3_id,
            market=market,
        )
    if path is None:
        raise ValueError(f"unknown sector path: {level1_id}/{level2_id}/{level3_id}")
    # Removed performance_cache usage
    response = await list_sector_constituents(
        registry.stock_store,
        registry.kline_store,
        registry.sector_precomputed_store,
        path,
        scope=scope,
        market=to_native_market_code(market) if market else None,
        days=days,
    )
    native_market = to_native_market_code(response.market) if response.market else None
    items = [item.model_dump(mode="json") | {"market": to_native_market_code(item.market) or item.market} for item in response.items]
    return SectorConstituentsResponseV1(
        level1_id=response.level1_id,
        level2_id=response.level2_id,
        level3_id=response.level3_id,
        scope=response.scope,
        market=native_market,
        count=len(items),
        items=items,
    )


async def build_ticker_quote_v1(registry, *, ticker: str, market: Optional[str]) -> Optional[TickerQuoteResponseV1]:
    internal_market = normalize_market_code(market)
    quote = resolve_core_ticker_quote(ticker, market=internal_market, stock_store=registry.stock_store)
    if quote is None:
        return None
    stock_market = normalize_market_code(quote.market) or internal_market or quote.market
    stock = registry.stock_store.get(stock_market, quote.ticker)
    sector_response = resolve_core_ticker_sector(
        ticker,
        market=internal_market,
        stock_store=registry.stock_store,
        stock_sector_store=registry.stock_sector_store,
        sector_store=registry.sector_store,
    )
    payload = quote.model_dump()
    payload["market"] = to_native_market_code(quote.market) or quote.market
    payload["name"] = _safe_stock_bilingual_name(stock, quote.ticker)
    payload["sector_paths"] = [_sector_option_to_path(option) for option in (sector_response.sector_options if sector_response else [])]
    return TickerQuoteResponseV1(**payload)


async def build_ticker_financials_v1(
    registry,
    *,
    ticker: str,
    market: Optional[str],
    start_date: Optional[str],
    end_date: Optional[str],
    limit: Optional[int],
    report_type: Optional[str],
) -> Optional[TickerFinancialsResponseV1]:
    internal_market = normalize_market_code(market) or "us"
    response, income = await asyncio.gather(
        registry.stock_fin_indicators_store.get_for_ticker(
            ticker,
            market=internal_market,
            limit=limit or 20,
        ),
        registry.stock_income_store.get_for_ticker(
            ticker,
            market=internal_market,
            page_size=100,
        ),
    )
    filtered = filter_date_rows(
        response.items,
        start_date=start_date,
        end_date=end_date,
        extract_date=lambda row: row.get("std_report_date") or row.get("report_date"),
    )
    distributions = []
    for item in income.distributions:
        data = item.model_dump(mode="json") if hasattr(item, "model_dump") else dict(item)
        distributions.append(
            IncomeDistributionSlice(
                dimension=_income_dimension(data.get("mainop_type")),
                report_date=data.get("report_date"),
                items=[
                    {
                        "name": entry.get("item_name") or entry.get("name") or "",
                        "main_business_income": float(entry.get("main_business_income") or 0.0),
                        "ratio": float(entry.get("mbi_ratio") or entry.get("ratio") or 0.0),
                    }
                    for entry in data.get("items", [])
                ],
            )
        )
    period_start, period_end = _date_bounds(filtered, "std_report_date", "report_date")
    return TickerFinancialsResponseV1(
        ticker=response.ticker,
        market=to_native_market_code(response.market) or response.market,
        report_type=report_type or response.report_type or report_type_for_market(internal_market),
        as_of=response.as_of,
        period_start=period_start,
        period_end=period_end,
        indicators=filtered,
        income_distributions=distributions,
    )


async def build_ticker_news_events_v1(
    registry,
    *,
    ticker: str,
    market: Optional[str],
    start_date: Optional[str],
    end_date: Optional[str],
    page_size: Optional[int],
) -> Optional[TickerNewsEventsResponseV1]:
    internal_market = normalize_market_code(market) or "us"
    news, events = await asyncio.gather(
        registry.stock_news_store.get_for_ticker(
            ticker,
            market=internal_market,
            page_size=page_size or 20,
        ),
        registry.stock_event_store.get_for_ticker(
            ticker,
            market=internal_market,
            page_size=page_size or 20,
        ),
    )
    news_items = filter_date_rows(
        news.items,
        start_date=start_date,
        end_date=end_date,
        extract_date=lambda row: row.get("publish_date"),
    )
    event_items = filter_date_rows(
        events.items,
        start_date=start_date,
        end_date=end_date,
        extract_date=lambda row: row.get("event_date") or row.get("remind_date") or row.get("notice_date"),
    )
    combined_dates = []
    for row in news_items:
        raw = row.get("publish_date") or row.get("published_at")
        if raw:
            combined_dates.append(str(raw)[:10])
    for row in event_items:
        raw = row.get("event_date") or row.get("remind_date") or row.get("notice_date")
        if raw:
            combined_dates.append(str(raw)[:10])
    return TickerNewsEventsResponseV1(
        ticker=ticker.strip().upper(),
        market=to_native_market_code(internal_market) or internal_market,
        period_start=min(combined_dates) if combined_dates else None,
        period_end=max(combined_dates) if combined_dates else None,
        news=[
            TickerNewsItem(
                title=str(item.get("title") or ""),
                summary=str(item.get("summary") or item.get("content") or ""),
                published_at=item.get("published_at") or item.get("publish_date"),
                source=item.get("source"),
                url=item.get("url"),
            )
            for item in news_items
        ],
        events=[
            TickerEventItem(
                event_type=str(item.get("event_type") or item.get("type") or ""),
                title=str(item.get("title") or item.get("event_name") or ""),
                event_date=item.get("event_date") or item.get("remind_date") or item.get("notice_date"),
                description=str(item.get("level1_content") or item.get("level2_content") or ""),
            )
            for item in event_items
        ],
    )


async def build_ticker_price_trends_v1(
    registry,
    *,
    ticker: str,
    market: Optional[str],
    start_date: Optional[str],
    end_date: Optional[str],
    limit: Optional[int],
    kline_t: str = "1D",
) -> Optional[TickerPriceTrendsResponseV1]:
    internal_market = normalize_market_code(market)
    symbol = ticker.strip().upper()
    resolved_limit = limit or 252
    kline = await registry.kline_store.get_or_fetch_kline(
        symbol,
        market=internal_market,
        kline_t=kline_t,
        start_time=start_date,
        end_time=end_date,
        limit=resolved_limit,
    )
    if kline is None:
        return None
    try:
        fin_response = await registry.stock_fin_indicators_store.get_for_ticker(
            symbol,
            market=internal_market or "us",
            limit=max(24, min(50, resolved_limit // 10 + 8)),
        )
        fin_rows = fin_response.items
    except ValueError:
        fin_rows = None
    pe_band: CoreTickerPeBandResponse | None = await resolve_core_ticker_pe_band(
        symbol,
        market=internal_market,
        limit=resolved_limit,
        stock_store=registry.stock_store,
        kline_store=registry.kline_store,
        fin_indicators_store=registry.stock_fin_indicators_store,
        fin_rows=fin_rows,
    )
    bars = list(kline.bars)
    period_start, period_end = _date_bounds(bars, "bar_time", "datetime", "date")
    return TickerPriceTrendsResponseV1(
        ticker=symbol,
        market=to_native_market_code(internal_market) or internal_market or "us",
        interval=kline_t,
        as_of=kline.as_of,
        period_start=period_start,
        period_end=period_end,
        klines=[
            {
                "datetime": _model_dict(bar).get("bar_time") or _model_dict(bar).get("datetime") or _model_dict(bar).get("date") or "",
                "open": float(_model_dict(bar).get("open") or 0.0),
                "high": float(_model_dict(bar).get("high") or 0.0),
                "low": float(_model_dict(bar).get("low") or 0.0),
                "close": float(_model_dict(bar).get("close") or 0.0),
                "volume": _model_dict(bar).get("vol") or _model_dict(bar).get("volume"),
            }
            for bar in bars
        ],
        pe_band=[PeBandPoint(**point.model_dump()) for point in (pe_band.points if pe_band else [])],
    )


async def build_portfolio_list_v1(registry, *, query: Optional[str]) -> PortfolioListResponseV1:
    if query:
        search = await registry.portfolio_service.search(query)
        detail_map = {item.id: await registry.portfolio_service.get_detail(item.id, include_performance=False) for item in search.items}
        items = [detail for detail in detail_map.values() if detail is not None]
    else:
        items = await registry.portfolio_service.list_summaries()
    return PortfolioListResponseV1(query=query, items=[_portfolio_summary_item(item) for item in items])


async def build_portfolio_analysis_v1(
    registry,
    *,
    portfolio_id: str,
    benchmark: Optional[str],
    start_date: Optional[str],
    include_performance: bool,
) -> Optional[PortfolioAnalysisResponseV1]:
    benchmark_by_market = dict(DEFAULT_BENCHMARKS)
    if benchmark:
        normalized = benchmark.strip()
        for key in benchmark_by_market:
            benchmark_by_market[key] = normalized
    detail = await registry.portfolio_service.get_detail(
        portfolio_id,
        include_performance=include_performance,
        benchmark_by_market=benchmark_by_market,
    )
    if detail is None:
        return None
    if start_date and detail.config is not None:
        detail = detail.model_copy(
            update={
                "config": detail.config.model_copy(update={"start_date": start_date}),
            }
        )
    return _portfolio_analysis(detail)


def build_update_request_from_manage(body) -> UpdatePortfolioRequest:
    config = None
    if body.config is not None:
        config = PortfolioCapitalConfig.model_validate(body.config)
    elif body.start_date or body.capital_by_market:
        config = PortfolioCapitalConfig(
            start_date=body.start_date or date.today().isoformat(),
            capital_by_market=body.capital_by_market or {},
        )
    return UpdatePortfolioRequest(
        name=body.name,
        pinned=body.pinned,
        config=config,
        shares_by_ticker=body.shares_by_ticker,
        manual_shares_by_ticker=body.manual_shares_by_ticker,
        open_date_by_ticker=body.open_date_by_ticker,
        shares_locked_by_ticker=body.shares_locked_by_ticker,
        open_date_locked_by_ticker=body.open_date_locked_by_ticker,
        cost_locked_by_ticker=body.cost_locked_by_ticker,
        cost_override_by_ticker=body.cost_override_by_ticker,
    )
