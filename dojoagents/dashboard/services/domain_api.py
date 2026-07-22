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
    PortfolioCandidateRow,
    PortfolioHoldingRow,
    PortfolioKpi,
    PortfolioOrderRow,
    PeBandPoint,
    PortfolioAnalysisResponseV1,
    PortfolioListResponseV1,
    PortfolioPerformanceResponseV1,
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
    TickerFinancialsBatchResponseV1,
    TickerNewsItem,
    TickerNewsEventsResponseV1,
    TickerPriceTrendsResponseV1,
    TickerQuoteResponseV1,
    TickerQuotesBatchResponseV1,
    TickerSectorPath,
    IncomeDistributionSlice,
    MAX_TICKER_QUOTES_BATCH,
    MAX_TICKER_FINANCIALS_BATCH,
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
    finite_float,
    finite_optional_float,
    normalize_market_code,
    to_native_market_code,
)
from dojoagents.dashboard.services.dojo_core_fin import (
    resolve_fin_indicators_for_market,
    resolve_income_for_market,
)
from dojoagents.dashboard.services.fin_indicators_utils import report_type_for_market
from dojoagents.dashboard.services.kline_bar_utils import DATA_START_DATE, resolve_tail_limit
from dojoagents.dashboard.services.ticker_symbol_resolution import resolve_ticker_symbol
from dojoagents.dashboard.services.market_sector_lead import (
    MAX_SECTOR_MEMBERS,
    _stock_bilingual_name,
    concept_code_for,
)
from dojoagents.dashboard.services.market_window import MarketAnalysisWindow, resolve_market_analysis_window
from dojoagents.dashboard.services.sector_movers_ranking import sector_eligible_for_movers_ranking
from dojoagents.dashboard.services.sector_leader_concentration import compute_leader_concentration
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
        total_market_cap=finite_float(data.get("total_market_cap")),
        weighted_pe=finite_optional_float(data.get("weighted_pe")),
        simple_pe=finite_optional_float(data.get("simple_pe")),
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
        price=finite_float(data.get("price")),
        change_percent=finite_float(data.get("change_percent")),
        window_start=data.get("window_start") or (dates[0] if dates else None),
        window_end=data.get("window_end") or (dates[-1] if dates else None),
        kline=[
            BenchmarkKlinePoint(
                datetime=str(_model_dict(bar).get("datetime") or _model_dict(bar).get("date") or ""),
                close=finite_float(_model_dict(bar).get("close")),
            )
            for bar in bars
        ],
    )


def _sector_member(member: Any) -> SectorMoverMember:
    data = _model_dict(member)
    return SectorMoverMember(
        ticker=str(data.get("ticker") or ""),
        name=BilingualText.model_validate(data.get("name") or {}),
        last_price=finite_float(data.get("last_price")),
        market_cap=finite_float(data.get("market_cap")),
        change_percent=finite_float(data.get("change_percent")),
    )


def _sector_mover_item(item: Any) -> SectorMoverItem:
    data = _model_dict(item)
    members = list(data.get("top_members") or data.get("members") or [])
    member_count = int(data.get("member_count") or len(members))
    avg_market_cap = finite_float(data.get("avg_market_cap"))
    total_market_cap = finite_float(data.get("total_market_cap"))
    if total_market_cap == 0.0 and avg_market_cap and member_count:
        total_market_cap = avg_market_cap * member_count
    return SectorMoverItem(
        level1_id=str(data.get("level1_id") or ""),
        level2_id=str(data.get("level2_id") or ""),
        level3_id=str(data.get("level3_id") or ""),
        concept_code=str(data.get("concept_code") or ""),
        name=BilingualText.model_validate(data.get("name") or {}),
        change_percent=finite_float(data.get("change_percent")),
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
        points.append(SectorPerformancePoint(date=str(date_value), value=finite_float(value)))
    return points


def _risk_stats(value: Any) -> SectorPerformanceStats:
    data = _model_dict(value)
    return SectorPerformanceStats(
        cumulative_return_pct=finite_optional_float(data.get("cumulative_return_pct")),
        sharpe_ratio=finite_optional_float(data.get("sharpe_ratio")),
        max_drawdown_pct=finite_optional_float(data.get("max_drawdown_pct")),
        calmar_ratio=finite_optional_float(data.get("calmar_ratio")),
        volatility_pct=finite_optional_float(data.get("volatility_pct")),
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
        quote = getattr(stock, "stock_quote", None)
        quote_name = getattr(quote, "name", None) if quote is not None else None
        zh = quote_name or getattr(stock, "short_name", None) or getattr(stock, "name", None) or getattr(stock, "ticker", None) or fallback
        en = getattr(stock, "short_name", None) or getattr(stock, "long_name", None) or getattr(stock, "ticker", None) or fallback
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


def _candidate_row(item: Any) -> PortfolioCandidateRow:
    data = _model_dict(item)
    return PortfolioCandidateRow(
        ticker=str(data.get("ticker") or ""),
        name=str(data.get("name") or data.get("ticker") or ""),
        name_zh=str(data.get("name_zh") or ""),
        name_en=str(data.get("name_en") or ""),
        market=to_native_market_code(data.get("market")) or str(data.get("market") or ""),
        price=finite_float(data.get("price")),
        change_percent=finite_float(data.get("change_percent")),
        market_cap=finite_float(data.get("market_cap")),
        pe=finite_optional_float(data.get("pe")),
        pb=finite_optional_float(data.get("pb")),
        dividend_yield=finite_optional_float(data.get("dividend_yield")),
        eps=finite_optional_float(data.get("eps")),
        turn_rate=finite_optional_float(data.get("turn_rate")),
        sector_l1=str(data.get("sector_l1") or ""),
        sector_l2=str(data.get("sector_l2") or ""),
        sector_l3=str(data.get("sector_l3") or ""),
    )


def _order_row(item: Any) -> PortfolioOrderRow:
    data = _model_dict(item)
    side = str(data.get("order_side") or "buy")
    kind = str(data.get("order_kind") or "trade")
    status = str(data.get("order_status") or "pending")
    if side not in {"buy", "sell", "set"}:
        side = "buy"
    if kind not in {"trade", "sync"}:
        kind = "trade"
    return PortfolioOrderRow(
        id=str(data.get("id") or ""),
        ticker=str(data.get("ticker") or ""),
        name=str(data.get("name") or data.get("ticker") or ""),
        name_zh=str(data.get("name_zh") or ""),
        name_en=str(data.get("name_en") or ""),
        market=to_native_market_code(data.get("market")) or str(data.get("market") or ""),
        order_side=side,  # type: ignore[arg-type]
        order_kind=kind,  # type: ignore[arg-type]
        order_status=status if status in {"pending", "filled", "cancelled", "rejected"} else "pending",
        price=finite_float(data.get("price")),
        qty=finite_float(data.get("qty")),
        order_time=data.get("order_time"),
        fill_time=data.get("fill_time"),
        fill_price=finite_optional_float(data.get("fill_price")),
        created_at=str(data.get("created_at") or ""),
        source=data.get("source"),
        sync_note=data.get("sync_note"),
    )


def _holding_row(item: Any) -> PortfolioHoldingRow:
    data = _model_dict(item)
    return PortfolioHoldingRow(
        ticker=str(data.get("ticker") or ""),
        name=str(data.get("name") or data.get("ticker") or ""),
        name_zh=str(data.get("name_zh") or ""),
        name_en=str(data.get("name_en") or ""),
        market=to_native_market_code(data.get("market")) or str(data.get("market") or ""),
        shares=finite_float(data.get("shares")),
        weight=finite_float(data.get("weight")),
        cost=finite_float(data.get("cost")),
        cost_low=finite_optional_float(data.get("cost_low")),
        cost_high=finite_optional_float(data.get("cost_high")),
        uses_default_cost=bool(data.get("uses_default_cost", True)),
        cost_date=data.get("cost_date"),
        open_date=data.get("open_date"),
        uses_default_open_date=bool(data.get("uses_default_open_date", True)),
        cost_basis=finite_float(data.get("cost_basis")),
        price=finite_float(data.get("price")),
        change_percent=finite_float(data.get("change_percent")),
        total_return_pct=finite_optional_float(data.get("total_return_pct")),
        market_value=finite_float(data.get("market_value")),
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
        points.append(SectorPerformancePoint(date=str(dates[index]), value=finite_float(value)))
    return points


def _portfolio_analysis(detail: Any) -> PortfolioAnalysisResponseV1:
    data = _model_dict(detail)
    config = _model_dict(data.get("config") or {})
    performance = _model_dict(data.get("performance") or {})
    dates = list(performance.get("dates") or [])
    nav_by_market: dict[str, list[SectorPerformancePoint]] = {}
    benchmark_by_market: dict[str, list[SectorPerformancePoint]] = {}
    stats_by_market: dict[str, SectorPerformanceStats] = {}
    candidate_nav_by_market: dict[str, list[SectorPerformancePoint]] = {}
    candidate_stats_by_market: dict[str, SectorPerformanceStats] = {}
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
    for market, points in (performance.get("candidate_series_by_market") or {}).items():
        market_key = to_native_market_code(market) or market
        candidate_nav_by_market[market_key] = _performance_points(points)
    for market, stats in (performance.get("candidate_stats_by_market") or {}).items():
        market_key = to_native_market_code(market) or market
        candidate_stats_by_market[market_key] = _risk_stats(stats)

    raw_benchmark_by_market = performance.get("benchmark_by_market") or {}
    raw_benchmark_symbols = performance.get("benchmark_symbol_by_market") or {}
    for market, points in candidate_nav_by_market.items():
        if not nav_by_market.get(market):
            nav_by_market[market] = points
        if market not in stats_by_market and market in candidate_stats_by_market:
            stats_by_market[market] = candidate_stats_by_market[market]
        if market not in benchmark_by_market:
            internal_market = normalize_market_code(market) or market
            bench_values = raw_benchmark_by_market.get(internal_market) or raw_benchmark_by_market.get(market)
            if bench_values and points:
                dates = [point.date for point in points]
                benchmark_by_market[market] = _market_performance_points(dates, list(bench_values))
            symbol = raw_benchmark_symbols.get(internal_market) or raw_benchmark_symbols.get(market)
            if symbol:
                benchmark_symbol_by_market[market] = str(symbol)
    if not nav_by_market and dates:
        nav_by_market["all"] = _market_performance_points(dates, list(performance.get("portfolio") or []))
        benchmark_by_market["all"] = _market_performance_points(dates, list(performance.get("benchmark") or []))
    net_value_by_market = data.get("net_value_by_market") or {}
    net_value_usd = data.get("net_value_usd")
    if net_value_usd is None and net_value_by_market:
        net_value_usd = finite_float(sum(float(value or 0) for value in net_value_by_market.values()))
    return PortfolioAnalysisResponseV1(
        id=str(data.get("id") or ""),
        name=str(data.get("name") or ""),
        subtitle=data.get("subtitle"),
        kind=data.get("kind") or "manual",
        pinned=bool(data.get("pinned", False)),
        today_change=finite_optional_float(data.get("today_change")),
        net_value_usd=finite_optional_float(net_value_usd),
        benchmark=data.get("benchmark"),
        start_date=config.get("start_date"),
        capital_by_market={to_native_market_code(market) or market: finite_float(value) for market, value in (config.get("capital_by_market") or {}).items()},
        candidates=[_candidate_row(item) for item in data.get("candidates") or []],
        holdings=[_holding_row(item) for item in data.get("positions") or data.get("holdings") or []],
        kpis=[_portfolio_kpi(item) for item in data.get("kpis") or []],
        performance_window_start=performance.get("window_start"),
        performance_window_end=performance.get("window_end"),
        nav_by_market=nav_by_market,
        candidate_nav_by_market=candidate_nav_by_market,
        benchmark_by_market=benchmark_by_market,
        benchmark_symbol_by_market=benchmark_symbol_by_market,
        stats_by_market=stats_by_market,
        candidate_stats_by_market=candidate_stats_by_market,
        net_value_by_market={to_native_market_code(market) or market: finite_float(value) for market, value in (data.get("net_value_by_market") or {}).items()},
        cost_basis_by_market={to_native_market_code(market) or market: finite_float(value) for market, value in (data.get("cost_basis_by_market") or {}).items()},
        orders=[_order_row(item) for item in data.get("orders") or []],
    )


def portfolio_detail_to_analysis(detail: Any) -> PortfolioAnalysisResponseV1:
    return _portfolio_analysis(detail)


def _portfolio_performance_response(
    *,
    portfolio_id: str,
    performance: Any,
    benchmark: Optional[str] = None,
    start_date: Optional[str] = None,
) -> PortfolioPerformanceResponseV1:
    data = _model_dict(performance or {})
    dates = list(data.get("dates") or [])
    nav_by_market: dict[str, list[SectorPerformancePoint]] = {}
    benchmark_by_market: dict[str, list[SectorPerformancePoint]] = {}
    stats_by_market: dict[str, SectorPerformanceStats] = {}
    candidate_nav_by_market: dict[str, list[SectorPerformancePoint]] = {}
    candidate_stats_by_market: dict[str, SectorPerformanceStats] = {}
    benchmark_symbol_by_market = {
        to_native_market_code(market) or market: str(symbol)
        for market, symbol in (data.get("benchmark_symbol_by_market") or {}).items()
    }
    for market, series in (data.get("series_by_market") or {}).items():
        series_data = _model_dict(series)
        market_key = to_native_market_code(market) or market
        market_dates = list(series_data.get("dates") or dates)
        nav_by_market[market_key] = _market_performance_points(market_dates, list(series_data.get("portfolio") or []))
        benchmark_by_market[market_key] = _market_performance_points(market_dates, list(series_data.get("benchmark") or []))
        stats_by_market[market_key] = _risk_stats(series_data.get("stats") or {})
        if series_data.get("benchmark_symbol"):
            benchmark_symbol_by_market[market_key] = str(series_data["benchmark_symbol"])
    for market, points in (data.get("candidate_series_by_market") or {}).items():
        market_key = to_native_market_code(market) or market
        candidate_nav_by_market[market_key] = _performance_points(points)
    for market, stats in (data.get("candidate_stats_by_market") or {}).items():
        market_key = to_native_market_code(market) or market
        candidate_stats_by_market[market_key] = _risk_stats(stats)
    raw_benchmark_by_market = data.get("benchmark_by_market") or {}
    raw_benchmark_symbols = data.get("benchmark_symbol_by_market") or {}
    for market, points in candidate_nav_by_market.items():
        if not nav_by_market.get(market):
            nav_by_market[market] = points
        if market not in stats_by_market and market in candidate_stats_by_market:
            stats_by_market[market] = candidate_stats_by_market[market]
        if market not in benchmark_by_market:
            internal_market = normalize_market_code(market) or market
            bench_values = raw_benchmark_by_market.get(internal_market) or raw_benchmark_by_market.get(market)
            if bench_values and points:
                point_dates = [point.date for point in points]
                benchmark_by_market[market] = _market_performance_points(point_dates, list(bench_values))
            symbol = raw_benchmark_symbols.get(internal_market) or raw_benchmark_symbols.get(market)
            if symbol:
                benchmark_symbol_by_market[market] = str(symbol)
    if not nav_by_market and dates:
        nav_by_market["all"] = _market_performance_points(dates, list(data.get("portfolio") or []))
        benchmark_by_market["all"] = _market_performance_points(dates, list(data.get("benchmark") or []))
    return PortfolioPerformanceResponseV1(
        id=portfolio_id,
        benchmark=benchmark,
        start_date=start_date,
        performance_window_start=data.get("window_start"),
        performance_window_end=data.get("window_end"),
        nav_by_market=nav_by_market,
        candidate_nav_by_market=candidate_nav_by_market,
        benchmark_by_market=benchmark_by_market,
        benchmark_symbol_by_market=benchmark_symbol_by_market,
        stats_by_market=stats_by_market,
        candidate_stats_by_market=candidate_stats_by_market,
    )


def _precomputed_market_candidates(market: Optional[str]) -> list[Optional[str]]:
    native_market = to_native_market_code(market) if market else None
    internal_market = normalize_market_code(market) if market else None
    candidates: list[Optional[str]] = []
    for candidate in (native_market, internal_market, market):
        if candidate not in candidates:
            candidates.append(candidate)
    return candidates or [None]


class SectorPathResolutionError(ValueError):
    def __init__(self, message: str, *, suggestions: list[Any] | None = None) -> None:
        super().__init__(message)
        self.suggestions = list(suggestions or [])


def _looks_like_index_guess(level1_id: str, level2_id: str, level3_id: str) -> bool:
    parts = (level1_id.strip(), level2_id.strip(), level3_id.strip())
    if not all(parts):
        return False
    if all(part.isdigit() for part in parts):
        return True
    if len(set(parts)) == 1 and parts[0].isdigit():
        return True
    return False


def _collect_sector_path_suggestions(
    store: Any,
    *,
    query: str = "",
    limit: int = 3,
) -> list[Any]:
    needle = str(query or "").strip()
    if not needle:
        return []
    return store.search_resolved_paths(needle, limit=limit)


def _append_sector_path_suggestions(message: str, suggestions: list[Any]) -> str:
    if not suggestions:
        return message
    if "Did you mean:" in message:
        return message
    return message + " Did you mean: " + _format_sector_path_suggestions(suggestions) + "?"


def _raise_sector_path_resolution_error(
    message: str,
    *,
    suggestions: list[Any] | None = None,
) -> None:
    resolved_suggestions = list(suggestions or [])
    raise SectorPathResolutionError(
        _append_sector_path_suggestions(message, resolved_suggestions),
        suggestions=resolved_suggestions,
    )


def _format_sector_path_suggestions(paths: list[Any], *, limit: int = 3) -> str:
    lines: list[str] = []
    for path in paths[:limit]:
        label = path.level3_zh or path.level3_en or path.level3_id
        lines.append(f"{path.level1_id}/{path.level2_id}/{path.level3_id} ({label})")
    return "; ".join(lines)


def _format_sector_path_id(level1_id: str, level2_id: str, level3_id: str) -> str:
    return f"{level1_id}/{level2_id}/{level3_id}"


def _parse_sector_path_id(value: str) -> tuple[str, str, str] | None:
    text = str(value or "").strip()
    if not text or text.count("/") != 2:
        return None
    parts = [part.strip() for part in text.split("/", 2)]
    if not all(parts):
        return None
    return parts[0], parts[1], parts[2]


def _sector_path_id_format_error(path_id: str) -> str:
    segment_count = str(path_id or "").count("/") + 1 if str(path_id or "").strip() else 0
    if segment_count == 2:
        return (
            f"Invalid sector_path_id {path_id!r}: expected level1_id/level2_id/level3_id (three segments). "
            "scope=L2 does NOT mean a two-segment path. Copy the full sector_path_id from "
            "search_sector_taxonomy, then set scope='L2' to list all constituents under that L2 branch."
        )
    return (
        f"Invalid sector_path_id {path_id!r}. Expected format level1_id/level2_id/level3_id "
        "from search_sector_taxonomy."
    )


_SECTOR_CONCEPT_SYNONYMS: dict[str, tuple[str, ...]] = {
    "具身智能": ("机器人", "robotics", "robot", "自动化", "automation", "机械", "embodied"),
    "embodied ai": ("机器人", "robotics", "robot", "automation", "具身"),
    "embodied intelligence": ("机器人", "robotics", "robot", "automation"),
    "人工智能": ("ai", "artificial intelligence", "机器学习", "machine learning", "深度学习"),
    "ai": ("人工智能", "artificial intelligence", "机器学习", "machine learning"),
    "半导体": ("芯片", "chip", "semiconductor", "集成电路"),
    "chip": ("半导体", "芯片", "semiconductor"),
    "新能源": ("光伏", "solar", "风电", "wind", "储能", "battery", "electric vehicle", "ev"),
    "高息": ("dividend", "utility", "reit", "银行", "bank"),
    "机器人": ("robotics", "robot", "自动化", "automation", "具身智能"),
}


def _expand_sector_search_queries(query: str) -> list[str]:
    needle = str(query or "").strip()
    if not needle:
        return []
    lowered = needle.lower()
    expanded: list[str] = [needle]
    for key, synonyms in _SECTOR_CONCEPT_SYNONYMS.items():
        key_lower = key.lower()
        if key_lower == lowered or key_lower in lowered or lowered in key_lower:
            for term in synonyms:
                if term not in expanded:
                    expanded.append(term)
            if key not in expanded:
                expanded.append(key)
            continue
        for term in synonyms:
            term_lower = term.lower()
            if term_lower == lowered or term_lower in lowered or lowered in term_lower:
                if key not in expanded:
                    expanded.append(key)
                for related in synonyms:
                    if related not in expanded:
                        expanded.append(related)
                break
    return expanded


def _sector_search_item(path: Any, *, hit: Any | None = None) -> dict[str, Any]:
    sector_path_id = _format_sector_path_id(path.level1_id, path.level2_id, path.level3_id)
    matched_level = str(getattr(hit, "matched_level", "") or "L3")
    constituent_scope = matched_level if matched_level in {"L1", "L2", "L3"} else "L3"
    item: dict[str, Any] = {
        "sector_path_id": sector_path_id,
        "level1_id": path.level1_id,
        "level2_id": path.level2_id,
        "level3_id": path.level3_id,
        "level2_name_zh": path.level2_zh,
        "level2_name_en": path.level2_en,
        "level3_name_zh": path.level3_zh,
        "level3_name_en": path.level3_en,
        "breadcrumb_zh": " > ".join(
            part for part in (path.level1_zh, path.level2_zh, path.level3_zh) if part
        ),
        "breadcrumb_en": " > ".join(
            part for part in (path.level1_en, path.level2_en, path.level3_en) if part
        ),
        "scope_hint": (
            f"matched_level={matched_level}: use scope={constituent_scope!r} in filter_sector_constituents "
            "but always pass the full three sector ids (or sector_path_id)."
        ),
        "next_call": {
            "tool": "filter_sector_constituents",
            "arguments": {
                "sector_path_id": sector_path_id,
                "level1_id": path.level1_id,
                "level2_id": path.level2_id,
                "level3_id": path.level3_id,
                "market": "us",
                "scope": constituent_scope,
                "days": 1,
            },
        },
        "get_sector_analysis_example": {
            "sector_path_id": sector_path_id,
            "level1_id": path.level1_id,
            "level2_id": path.level2_id,
            "level3_id": path.level3_id,
            "scope": constituent_scope,
        },
    }
    if hit is not None:
        item["match_score"] = hit.score
        item["matched_level"] = hit.matched_level
        item["matched_label"] = hit.matched_label
        item["matched_via_query"] = hit.matched_query
    return item


def _looks_like_sector_label(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if any("\u4e00" <= char <= "\u9fff" for char in text):
        return True
    return any(char.isalpha() for char in text) and len(text) > 2


def resolve_sector_path(
    registry: Any,
    *,
    sector_path_id: str = "",
    level1_id: str = "",
    level2_id: str = "",
    level3_id: str = "",
    sector_name: Optional[str] = None,
    level1_name: Optional[str] = None,
    level2_name: Optional[str] = None,
    level3_name: Optional[str] = None,
    market: Optional[str] = None,
) -> Any:
    store = registry.sector_store
    path_id = str(sector_path_id or "").strip()
    if path_id:
        parsed = _parse_sector_path_id(path_id)
        if parsed is None:
            raise SectorPathResolutionError(_sector_path_id_format_error(path_id))
        l1, l2, l3 = parsed
        path = store.find_resolved_path(l1, l2, l3)
        if path is not None:
            return path
        suggestions = _collect_sector_path_suggestions(
            store,
            query=str(sector_name or level3_name or level2_name or level1_name or "").strip(),
        )
        if _looks_like_index_guess(l1, l2, l3):
            _raise_sector_path_resolution_error(
                f"Rejected guessed sector_path_id {path_id}. "
                "Call search_sector_taxonomy and copy sector_path_id or level1_id/level2_id/level3_id "
                "verbatim from best_match. Do not construct ids or use array indices.",
                suggestions=suggestions,
            )
        _raise_sector_path_resolution_error(
            f"unknown sector_path_id: {path_id}. "
            "Call search_sector_taxonomy with the concept keyword and copy ids from best_match.",
            suggestions=suggestions,
        )

    l1 = str(level1_id or "").strip()
    l2 = str(level2_id or "").strip()
    l3 = str(level3_id or "").strip()
    name_query = str(sector_name or level3_name or "").strip()

    if l1 and l2 and l3:
        path = store.find_resolved_path(l1, l2, l3)
        if path is not None:
            return path
        if not name_query and not level1_name and not level2_name and not level3_name:
            if _looks_like_index_guess(l1, l2, l3):
                suggestions = _collect_sector_path_suggestions(store, query=l3 or l2 or l1)
                _raise_sector_path_resolution_error(
                    f"Rejected guessed sector path {l1}/{l2}/{l3}. "
                    "Call search_sector_taxonomy and copy sector_path_id or level1_id/level2_id/level3_id "
                    "from best_match. Do not construct ids or use array indices.",
                    suggestions=suggestions,
                )

    if l1 and l2 and not l3 and not name_query:
        anchor = store.find_anchor_path_for_level2(l1, l2)
        if anchor is not None:
            return anchor

    if l1 and l1 == l2 == l3:
        path = store.find_resolved_path_by_any_sector_id(l1)
        if path is not None:
            return path

    if l3 and not l1 and not l2:
        path = store.find_resolved_path_by_level3_id(l3)
        if path is not None:
            return path

    label_path = store.find_resolved_path_by_labels(
        level_1_zh=level1_name or (l1 if _looks_like_sector_label(l1) else ""),
        level_1_en=level1_name or (l1 if _looks_like_sector_label(l1) else ""),
        level_2_zh=level2_name or (l2 if _looks_like_sector_label(l2) else ""),
        level_2_en=level2_name or (l2 if _looks_like_sector_label(l2) else ""),
        level_3_zh=level3_name or name_query or (l3 if _looks_like_sector_label(l3) else ""),
        level_3_en=level3_name or name_query or (l3 if _looks_like_sector_label(l3) else ""),
    )
    if label_path is not None:
        return label_path

    if name_query:
        matches = store.search_resolved_paths(name_query, limit=2)
        if len(matches) == 1:
            return matches[0]

    if l1 and l2 and l3:
        path = _fallback_precomputed_sector_path(
            registry,
            level1_id=l1,
            level2_id=l2,
            level3_id=l3,
            market=market,
        )
        if path is not None:
            return path

    query = name_query or (l3 if _looks_like_sector_label(l3) else "") or l3 or l2 or l1
    suggestions = store.search_resolved_paths(query, limit=3) if query else []
    attempted = "/".join(part for part in (l1, l2, l3) if part) or query or "?"
    message = (
        f"unknown sector path: {attempted}. "
        "Call search_sector_taxonomy with the concept keyword, pick the best match, then pass "
        "sector_path_id or level1_id/level2_id/level3_id verbatim."
    )
    if l1 and l2 and not l3:
        message += (
            " For L2-scope constituents, still pass all three ids from best_match "
            "(or level1_id+level2_id when uniquely resolved) and set scope='L2'."
        )
    _raise_sector_path_resolution_error(message, suggestions=suggestions)


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
    sector_name: Optional[str] = None,
    level1_name: Optional[str] = None,
    level2_name: Optional[str] = None,
    level3_name: Optional[str] = None,
    market: Optional[str] = None,
) -> Any | None:
    try:
        return resolve_sector_path(
            registry,
            level1_id=level1_id,
            level2_id=level2_id,
            level3_id=level3_id,
            sector_name=sector_name,
            level1_name=level1_name,
            level2_name=level2_name,
            level3_name=level3_name,
            market=market,
        )
    except SectorPathResolutionError:
        return None


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
        require_market_cap_eligible=False,
    )
    mapped = [_model_dict(item) | {"market": _normalize_native_market(item.market) or item.market} for item in items]
    return CompanyTickerSearchResponse(query=q.strip(), items=mapped)


def build_taxonomy_tree(registry) -> dict[str, Any]:
    document = registry.sector_store.to_taxonomy_document()
    data = document.model_dump(mode="json") if hasattr(document, "model_dump") else dict(document or {})
    tree = [
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
    ]

    example_l3_paths: list[dict[str, str]] = []
    for l1 in tree[:3]:
        l1_id = str(l1.get("level1_id") or "")
        for l2 in (l1.get("children") or [])[:2]:
            l2_id = str(l2.get("level2_id") or "")
            for l3 in (l2.get("children") or [])[:2]:
                l3_id = str(l3.get("level3_id") or "")
                if not (l1_id and l2_id and l3_id):
                    continue
                name = l3.get("name") or {}
                example_l3_paths.append(
                    {
                        "level1_id": l1_id,
                        "level2_id": l2_id,
                        "level3_id": l3_id,
                        "name_zh": str(name.get("zh") or ""),
                        "name_en": str(name.get("en") or ""),
                    }
                )
                if len(example_l3_paths) >= 5:
                    break
            if len(example_l3_paths) >= 5:
                break
        if len(example_l3_paths) >= 5:
            break

    first = example_l3_paths[0] if example_l3_paths else None
    filter_example = None
    if first is not None:
        filter_example = {
            "level1_id": first["level1_id"],
            "level2_id": first["level2_id"],
            "level3_id": first["level3_id"],
            "market": "us",
            "scope": "L3",
            "days": 1,
        }

    return {
        "version": data.get("version") or "api",
        "id_scheme": data.get("id_scheme") or "sector_id",
        "usage": (
            "Copy level1_id, level2_id, level3_id from the SAME L3 branch below. "
            "These are opaque sector_id strings (e.g. 153/160/161), NOT array indices 1/2/3."
        ),
        "playbook": {
            "step_1": "For keyword/concept requests use search_sector_taxonomy first; use get_taxonomy_tree for full tree.",
            "step_2": "Pick one entry from example_l3_paths OR search_sector_taxonomy results.",
            "step_3": "Call filter_sector_constituents with the three ids plus market.",
            "forbidden": "Never pass 1, 2, 3 or child index as ids. Never use search_company_ticker for themes.",
            "alternative": "Or call filter_sector_constituents with sector_name = exact L3 name_zh or name_en.",
        },
        "example_l3_paths": example_l3_paths,
        "filter_sector_constituents_example": filter_example,
        "tree": tree,
    }


def build_sector_taxonomy_search(registry, *, query: str, limit: int = 10) -> dict[str, Any]:
    needle = str(query or "").strip()
    if not needle:
        raise ValueError("query is required")

    store = registry.sector_store
    cap = max(1, min(limit, 25))
    search_queries = _expand_sector_search_queries(needle)
    best_hits: dict[tuple[str, str, str], Any] = {}
    for term in search_queries:
        for hit in store.search_resolved_paths_scored(term, limit=cap * 2):
            key = (hit.path.level1_id, hit.path.level2_id, hit.path.level3_id)
            existing = best_hits.get(key)
            if existing is None or hit.score > existing.score:
                best_hits[key] = hit

    ranked = sorted(
        best_hits.values(),
        key=lambda hit: (
            -hit.score,
            hit.path.level3_zh or hit.path.level3_en or "",
            hit.path.level3_id,
        ),
    )[:cap]
    items = [_sector_search_item(hit.path, hit=hit) for hit in ranked]

    top = items[0] if items else None
    return {
        "query": needle,
        "expanded_queries": search_queries[1:] or None,
        "count": len(items),
        "id_resolution": (
            "Each item includes sector_path_id and level1_id/level2_id/level3_id. "
            "Copy them verbatim into filter_sector_constituents or get_sector_analysis — "
            "IDs resolve by exact lookup, not fuzzy name matching."
        ),
        "usage": (
            "1) Pick the highest match_score item. "
            "2) Copy sector_path_id from best_match — do NOT construct sector_path_id yourself. "
            "3) Call filter_sector_constituents with next_call.arguments (change market). "
            "4) Optional: get_sector_analysis with get_sector_analysis_example."
        ),
        "best_match": top,
        "items": items,
    }


async def build_market_overview(
    registry,
    *,
    days: int,
    market: Optional[str],
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> MarketOverviewResponse:
    window = resolve_market_analysis_window(
        days=days,
        start_date=start_date,
        end_date=end_date,
        default_days=days,
    )
    precomputed = getattr(registry, "sector_precomputed_store", None)
    if precomputed is not None:
        window = precomputed.resolve_window_bounds(window)
    benchmarks: DojoMeshBenchmarksResponse = await registry.benchmark_store.get_benchmarks(window=window)
    markets: dict[str, MarketStatsSnapshot] = {}
    benchmark_map: dict[str, list[BenchmarkSnapshot]] = {}
    requested_markets = [normalize_market_code(market)] if market else list(MARKETS)
    window_start = window.resolved_start
    window_end = window.resolved_end
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
        days=window.days,
        window_mode=window.mode,
        window_start=window.resolved_start or window_start,
        window_end=window.resolved_end or benchmarks.as_of or window_end,
        as_of=benchmarks.as_of or window.resolved_end or window_end,
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
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    include_members: bool = True,
) -> SectorMoversResponse:
    service = getattr(registry, "sector_movers_service", None)
    if service is not None:
        return await asyncio.to_thread(
            service.build_market_movers_response,
            days=days,
            limit=limit,
            market=market,
            min_cap_by_market=min_cap_by_market,
            start_date=start_date,
            end_date=end_date,
            include_members=include_members,
        )
    return await asyncio.to_thread(
        _build_sector_movers_fallback_sync,
        registry,
        days,
        limit,
        market,
        min_cap_by_market,
        start_date,
        end_date,
        include_members,
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
    from dojoagents.dashboard.services.stock_quote_filter import (
        change_significance_score,
        passes_market_cap_floor,
        stock_passes_market_screen_hard_filters,
    )

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
            if not stock_passes_market_screen_hard_filters(stock):
                continue
            universe_count += 1
            quote = stock.stock_quote
            assert quote is not None
            market_cap = quote.market_cap
            pe = quote.pe
            change_percent = quote.change_percent
            window_change_percent = None
            if not passes_market_cap_floor(
                internal_market,
                market_cap,
                min_market_cap=min_market_cap,
            ):
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
                    ticker=str(stock.ticker),
                    market=to_native_market_code(internal_market) or internal_market,
                    name=_safe_stock_bilingual_name(stock, str(stock.ticker)),
                    last_price=quote.last_price,
                    change_percent=change_percent,
                    window_change_percent=window_change_percent,
                    market_cap=market_cap,
                    pe=pe,
                    pb=quote.pb,
                )
            )
    sort_key = {
        "market_cap": lambda item: item.market_cap if item.market_cap is not None else float("-inf"),
        "return_pct": lambda item: change_significance_score(item.window_change_percent, item.market_cap),
        "change_percent": lambda item: change_significance_score(item.change_percent, item.market_cap),
        "pe": lambda item: item.pe if item.pe is not None else float("-inf"),
    }.get(sort_by, lambda item: item.market_cap if item.market_cap is not None else float("-inf"))
    significance_sort = sort_by in {"change_percent", "return_pct"}
    rows = sorted(rows, key=sort_key, reverse=True if significance_sort else sort_order == "desc")
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
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    include_members: bool = True,
) -> SectorMoversResponse:
    min_cap_by_market = min_cap_by_market or {}
    window = registry.sector_precomputed_store.resolve_window_bounds(
        resolve_market_analysis_window(
            days=days,
            start_date=start_date,
            end_date=end_date,
            default_days=days,
        )
    )
    requested_markets = [normalize_market_code(market)] if market else list(MARKETS)
    payload: dict[str, MarketSectorMovers] = {}

    sector_movers = registry.sector_precomputed_store.get_sector_movers_for_window(window)

    for internal_market in requested_markets:
        if internal_market is None:
            continue

        threshold = float(min_cap_by_market.get(internal_market) or 0.0)
        market_sectors = [s for s in sector_movers if s["market"] == internal_market and s["scope"] == "L3"]

        items: list[SectorMoverItem] = []
        for s in market_sectors:
            total_market_cap = finite_float(s.get("total_market_cap", 0))
            member_count = int(s.get("member_count") or 0)
            if not sector_eligible_for_movers_ranking(
                member_count=member_count,
                total_market_cap=total_market_cap,
                min_total_market_cap=threshold,
            ):
                continue

            path = registry.sector_store.find_resolved_path(
                s["level1_id"],
                s["level2_id"],
                s["level3_id"],
            )
            if path is None:
                continue

            if not include_members:
                items.append(
                    SectorMoverItem(
                        level1_id=str(s["level1_id"]),
                        level2_id=str(s["level2_id"]),
                        level3_id=str(s["level3_id"]),
                        concept_code=concept_code_for(internal_market, path.level3_zh, path.level3_en, "L3"),
                        name=BilingualText(zh=path.level3_zh, en=path.level3_en),
                        change_percent=round(finite_float(s.get("daily_return_pct")), 2),
                        avg_market_cap=(finite_float(total_market_cap) / member_count) if member_count else 0.0,
                        total_market_cap=finite_float(total_market_cap),
                        sample_tickers=[],
                        member_count=member_count,
                        top_members=[],
                    )
                )
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
            ticker_returns = registry.sector_precomputed_store.get_ticker_daily_for_window(
                window,
                tickers,
            )
            ticker_return_map = {tr["ticker"]: tr["daily_return_pct"] for tr in ticker_returns}

            members = []
            for c in constituents:
                stock = registry.stock_store.get(internal_market, c["ticker"])
                if not stock:
                    continue
                change = finite_float(ticker_return_map.get(c["ticker"], 0.0))
                members.append(
                    {
                        "ticker": c["ticker"],
                        "name": {"zh": stock.short_name or stock.ticker, "en": stock.long_name or stock.ticker},
                        "last_price": finite_float(stock.stock_quote.last_price if stock.stock_quote else 0.0),
                        "market_cap": finite_float(c.get("market_cap")),
                        "change_percent": round(change, 2),
                    }
                )

            sorted_members = sorted(members, key=lambda item: item["change_percent"], reverse=True)
            top_by_abs = sorted(members, key=lambda item: abs(item["change_percent"]), reverse=True)[:3]
            sector_change = round(finite_float(s.get("daily_return_pct")), 2)
            leader = compute_leader_concentration(
                [(m["ticker"], m.get("market_cap"), m.get("change_percent")) for m in members],
                sector_change,
            )

            item = SectorMoverItem(
                level1_id=str(s["level1_id"]),
                level2_id=str(s["level2_id"]),
                level3_id=str(s["level3_id"]),
                concept_code=concept_code_for(internal_market, path.level3_zh, path.level3_en, "L3"),
                name=BilingualText(zh=path.level3_zh, en=path.level3_en),
                change_percent=sector_change,
                avg_market_cap=(finite_float(total_market_cap) / s.get("member_count", 1)) if s.get("member_count") else 0.0,
                total_market_cap=finite_float(total_market_cap),
                sample_tickers=[m["ticker"] for m in top_by_abs],
                member_count=s.get("member_count", 0),
                top_members=[_sector_member(member) for member in sorted_members[:MAX_SECTOR_MEMBERS]],
                leader_ticker=leader.leader_ticker if leader else None,
                leader_weight_pct=round(leader.leader_weight_pct, 2) if leader else None,
                leader_return_pct=round(leader.leader_return_pct, 2) if leader else None,
                leader_contribution_pct=round(leader.leader_contribution_pct, 2) if leader else None,
                leader_concentration_pct=round(leader.leader_concentration_pct, 2) if leader else None,
                leader_concentration_tier=leader.leader_concentration_tier if leader else None,
            )
            items.append(item)

        gainers = sorted([item for item in items if item.change_percent > 0], key=lambda row: row.change_percent, reverse=True)[:limit]
        losers = sorted([item for item in items if item.change_percent < 0], key=lambda row: row.change_percent)[:limit]
        native_market = to_native_market_code(internal_market) or internal_market
        payload[native_market] = MarketSectorMovers(
            gainers=gainers,
            losers=losers,
        )
    return SectorMoversResponse(
        days=window.days,
        window_mode=window.mode,
        window_start=window.resolved_start,
        window_end=window.resolved_end,
        markets=payload,
    )


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

    metrics = await registry.dojo_sphere_service.metrics(
        f"{level1_id}/{level2_id}/{level3_id}",
        compute_metrics_payload,
    )
    scopes = {}
    sources: set[str] = set()
    stale = False

    async def load_scope_performance(current_scope: str) -> tuple[str, dict[str, Any]]:
        async def compute_performance_payload() -> dict[str, Any]:
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
        return current_scope, cached_performance

    for current_scope, cached_performance in await asyncio.gather(
        *(load_scope_performance(scope_key) for scope_key in ("L1", "L2", "L3")),
    ):
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
    sector_name: Optional[str] = None,
    level1_name: Optional[str] = None,
    level2_name: Optional[str] = None,
    level3_name: Optional[str] = None,
) -> SectorConstituentsResponseV1:
    path = resolve_sector_path(
        registry,
        level1_id=level1_id,
        level2_id=level2_id,
        level3_id=level3_id,
        sector_name=sector_name,
        level1_name=level1_name,
        level2_name=level2_name,
        level3_name=level3_name,
        market=market,
    )
    # Removed performance_cache usage
    response = await list_sector_constituents(
        registry.stock_store,
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


async def build_tickers_quotes_v1(
    registry,
    *,
    tickers: list[str],
    market: Optional[str],
) -> TickerQuotesBatchResponseV1:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in tickers:
        ticker = raw.strip().upper()
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        normalized.append(ticker)
    normalized = normalized[:MAX_TICKER_QUOTES_BATCH]

    results = await asyncio.gather(*(build_ticker_quote_v1(registry, ticker=ticker, market=market) for ticker in normalized))
    items = [item for item in results if item is not None]
    found = {item.ticker.upper() for item in items}
    not_found = [ticker for ticker in normalized if ticker not in found]
    return TickerQuotesBatchResponseV1(
        market=to_native_market_code(market) if market else None,
        count=len(items),
        not_found=not_found,
        items=items,
    )


def _indicator_has_valuation(row: dict[str, Any], metric: str) -> bool:
    if metric == "pe":
        keys = ("pe_ttm", "pe_ratio", "pe", "pe_dynamic")
    else:
        keys = ("pb_ttm", "pb_ratio", "pb")
    for key in keys:
        value = finite_optional_float(row.get(key))
        if value is not None and value > 0:
            return True
    return False


def _quote_valuation_metrics(registry, internal_market: str, ticker: str) -> tuple[float | None, float | None]:
    quote = resolve_core_ticker_quote(
        ticker,
        market=internal_market,
        stock_store=registry.stock_store,
    )
    if quote is None:
        return None, None
    pe = finite_optional_float(quote.pe)
    pb = finite_optional_float(quote.pb)
    return (
        pe if pe is not None and pe > 0 else None,
        pb if pb is not None and pb > 0 else None,
    )


def _enrich_indicator_valuation(
    rows: list[Any],
    *,
    pe: float | None,
    pb: float | None,
) -> list[dict[str, Any]]:
    normalized = [_model_dict(row) for row in rows]
    if not normalized or (pe is None and pb is None):
        return normalized
    latest = dict(normalized[-1])
    changed = False
    if pe is not None and not _indicator_has_valuation(latest, "pe"):
        latest["pe_ttm"] = pe
        changed = True
    if pb is not None and not _indicator_has_valuation(latest, "pb"):
        latest["pb_ttm"] = pb
        changed = True
    if not changed:
        return normalized
    return [*normalized[:-1], latest]


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
    raw_fin_items = list(response.items)
    forex_store = getattr(registry, "forex_store", None)
    response = await resolve_fin_indicators_for_market(
        response,
        forex_store=forex_store,
    )
    income = await resolve_income_for_market(
        income,
        forex_store=forex_store,
        fin_rows=raw_fin_items,
        market=internal_market,
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
    pe, pb = _quote_valuation_metrics(registry, internal_market, response.ticker)
    enriched = _enrich_indicator_valuation(filtered, pe=pe, pb=pb)
    return TickerFinancialsResponseV1(
        ticker=response.ticker,
        market=to_native_market_code(response.market) or response.market,
        report_type=report_type or response.report_type or report_type_for_market(internal_market),
        as_of=response.as_of,
        period_start=period_start,
        period_end=period_end,
        pe=pe,
        pb=pb,
        indicators=enriched,
        income_distributions=distributions,
    )


async def build_tickers_financials_v1(
    registry,
    *,
    tickers: list[str],
    market: Optional[str],
    start_date: Optional[str],
    end_date: Optional[str],
    limit: Optional[int],
    report_type: Optional[str],
) -> TickerFinancialsBatchResponseV1:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in tickers:
        ticker = raw.strip().upper()
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        normalized.append(ticker)
    normalized = normalized[:MAX_TICKER_FINANCIALS_BATCH]

    results = await asyncio.gather(
        *(
            build_ticker_financials_v1(
                registry,
                ticker=ticker,
                market=market,
                start_date=start_date,
                end_date=end_date,
                limit=limit,
                report_type=report_type,
            )
            for ticker in normalized
        )
    )
    items = [item for item in results if item is not None]
    found = {item.ticker.upper() for item in items}
    not_found = [ticker for ticker in normalized if ticker not in found]
    return TickerFinancialsBatchResponseV1(
        market=to_native_market_code(market) if market else None,
        count=len(items),
        not_found=not_found,
        items=items,
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


def _resolve_kline_symbol(
    stock_store,
    ticker: str,
    market: Optional[str],
) -> tuple[str, Optional[str]]:
    return resolve_ticker_symbol(stock_store, ticker, market)


async def _fetch_kline_for_price_trends(
    kline_store,
    *,
    symbol: str,
    market: str | None,
    kline_t: str,
    start_date: str | None,
    end_date: str | None,
    limit: int | None,
):
    """Fetch klines for price trends; fall back to wide-window local filter when date query is empty."""
    kline = await kline_store.get_or_fetch_kline(
        symbol,
        market=market,
        kline_t=kline_t,
        start_time=start_date,
        end_time=end_date,
        min_bar_time=None if start_date else DATA_START_DATE,
        limit=limit,
    )
    if kline is not None or not start_date or not end_date:
        return kline

    from dojoagents.dashboard.schemas.stock_kline import StockKlineResponse

    wide = await kline_store.get_or_fetch_kline(
        symbol,
        market=market,
        kline_t=kline_t,
        min_bar_time=DATA_START_DATE,
    )
    if wide is None:
        return None

    def _bar_day(bar: Any) -> str:
        if hasattr(bar, "bar_time"):
            return str(bar.bar_time or "")[:10]
        if hasattr(bar, "model_dump"):
            payload = bar.model_dump()
            return str(payload.get("bar_time") or payload.get("datetime") or "")[:10]
        return ""

    filtered = [bar for bar in wide.bars if start_date <= _bar_day(bar) <= end_date]
    if not filtered:
        return None
    return StockKlineResponse(symbol=symbol, as_of=_bar_day(filtered[-1]), bars=filtered)


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
    symbol, resolved_market = _resolve_kline_symbol(registry.stock_store, ticker, market)
    internal_market = resolved_market or internal_market
    resolved_limit = resolve_tail_limit(
        start_time=start_date,
        end_time=end_date,
        limit=limit,
    )
    kline = await _fetch_kline_for_price_trends(
        registry.kline_store,
        symbol=symbol,
        market=internal_market,
        kline_t=kline_t,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
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
    bars = list(kline.bars)
    pe_band: CoreTickerPeBandResponse | None = await resolve_core_ticker_pe_band(
        symbol,
        market=internal_market,
        limit=resolved_limit,
        start_time=start_date,
        end_time=end_date,
        kline_t=kline_t,
        stock_store=registry.stock_store,
        kline_store=registry.kline_store,
        fin_indicators_store=registry.stock_fin_indicators_store,
        fin_rows=fin_rows,
        bars=bars,
        as_of=kline.as_of,
    )
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
        from dojoagents.dashboard.services.portfolio_candidate_index import parse_candidate_index_symbol

        if not parse_candidate_index_symbol(normalized):
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


async def build_portfolio_summary_v1(
    registry,
    *,
    portfolio_id: str,
    start_date: Optional[str],
) -> Optional[PortfolioAnalysisResponseV1]:
    return await build_portfolio_analysis_v1(
        registry,
        portfolio_id=portfolio_id,
        benchmark=None,
        start_date=start_date,
        include_performance=False,
    )


async def build_portfolio_performance_v1(
    registry,
    *,
    portfolio_id: str,
    benchmark: Optional[str],
    start_date: Optional[str],
) -> Optional[PortfolioPerformanceResponseV1]:
    benchmark_by_market = dict(DEFAULT_BENCHMARKS)
    if benchmark:
        normalized = benchmark.strip()
        from dojoagents.dashboard.services.portfolio_candidate_index import parse_candidate_index_symbol

        if not parse_candidate_index_symbol(normalized):
            for key in benchmark_by_market:
                benchmark_by_market[key] = normalized
    performance = await registry.portfolio_service.get_performance(
        portfolio_id,
        benchmark_by_market=benchmark_by_market,
        start_date=start_date,
    )
    if performance is None:
        detail = await registry.portfolio_service.get_detail(
            portfolio_id,
            include_performance=False,
        )
        if detail is None:
            return None
        return PortfolioPerformanceResponseV1(id=portfolio_id)
    return _portfolio_performance_response(
        portfolio_id=portfolio_id,
        performance=performance,
        benchmark=benchmark,
        start_date=start_date,
    )


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
        kind=body.kind,
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
