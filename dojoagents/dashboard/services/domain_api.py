from __future__ import annotations
import asyncio
from typing import Any, Optional
from datetime import date
from dojoagents.dashboard.schemas.benchmark import DojoMeshBenchmarksResponse
from dojoagents.dashboard.schemas.dojo_core import CoreTickerPeBandResponse
from dojoagents.dashboard.schemas.dojo_mesh import BilingualText, SectorItem
from dojoagents.dashboard.schemas.domain_api import (
    CompanyTickerSearchResponse,
    FreshnessEnvelope,
    MarketOverviewMarket,
    MarketOverviewResponse,
    PeBandPoint,
    PortfolioAnalysisResponseV1,
    PortfolioListResponseV1,
    SectorAnalysisResponse,
    SectorAnalysisScope,
    SectorConstituentsResponseV1,
    SectorMoversMarket,
    SectorMoversResponse,
    TickerFinancialsResponseV1,
    TickerNewsEventsResponseV1,
    TickerPriceTrendsResponseV1,
    TickerQuoteResponseV1,
)
from dojoagents.dashboard.schemas.portfolio import (
    PortfolioCapitalConfig,
    UpdatePortfolioRequest,
)
from dojoagents.dashboard.services.constituent_window_change import close_at_window_start
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
from dojoagents.dashboard.services.kline_segment import latest_segment_ohlc
from dojoagents.dashboard.services.market_sector_lead import (
    MAX_SECTOR_MEMBERS,
    _apply_strength,
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


def _envelope(*, as_of=None, source=None, stale=False) -> FreshnessEnvelope:
    return FreshnessEnvelope(as_of=as_of, source=source, stale=bool(stale))


def _sector_scope_cache_key(level1_id: str, level2_id: str, level3_id: str, scope: str) -> str:
    return f"{scope}/{level1_id}/{level2_id}/{level3_id}"


def _normalize_native_market(market: Optional[str]) -> Optional[str]:
    normalized = normalize_market_code(market)
    return to_native_market_code(normalized)


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
        registry.stock_sector_store,
        registry.sector_store,
        q,
        market=internal_market,
        limit=limit,
    )
    mapped = [item.model_copy(update={"market": _normalize_native_market(item.market) or item.market}) for item in items]
    return CompanyTickerSearchResponse(query=q.strip(), items=mapped)


def build_taxonomy_tree(registry) -> dict[str, Any]:
    return registry.sector_store.to_taxonomy_document().model_dump()


async def build_market_overview(
    registry,
    *,
    days: int,
    market: Optional[str],
) -> MarketOverviewResponse:
    benchmarks: DojoMeshBenchmarksResponse = await registry.benchmark_store.get_benchmarks()
    markets = {}
    requested_markets = [normalize_market_code(market)] if market else list(MARKETS)
    for internal_market in requested_markets:
        if internal_market is None:
            continue
        stats = compute_market_stats(
            to_native_market_code(internal_market) or internal_market,
            registry.stock_store.list_market(internal_market),
        )
        benchmark_payload = benchmarks.markets.get(internal_market) if benchmarks.markets else None
        benchmark_list = []
        window_start = None
        window_end = None
        if benchmark_payload is not None:
            benchmark_list = [item.model_dump() for item in benchmark_payload.benchmarks]
            for benchmark in benchmark_payload.benchmarks:
                bars = benchmark.kline or []
                if bars:
                    dates = [bar.date for bar in bars if getattr(bar, "date", None)]
                    if dates:
                        start = dates[0]
                        end = dates[-1]
                        window_start = start if window_start is None else min(window_start, start)
                        window_end = end if window_end is None else max(window_end, end)
        native_market = to_native_market_code(internal_market) or internal_market
        markets[native_market] = MarketOverviewMarket(
            market=native_market,
            stats=stats,
            default_benchmark=benchmark_payload.default_benchmark if benchmark_payload else None,
            benchmarks=benchmark_list,
            window_start=window_start,
            window_end=window_end,
        )
    return MarketOverviewResponse(
        days=days,
        markets=markets,
        as_of=benchmarks.as_of,
        source="dashboard_cache",
        stale=False,
    )


def _window_percent_from_bars(bars: list, days: int) -> Optional[float]:
    segment = latest_segment_ohlc(bars)
    if segment is None or not segment.closes:
        return None
    ordered_dates = sorted(segment.closes)
    end_day = ordered_dates[-1]
    end_close = segment.closes[end_day]
    if end_close <= 0:
        return None
    if days <= 1:
        start_day = ordered_dates[-2] if len(ordered_dates) >= 2 else ordered_dates[0]
    else:
        start_index = max(0, len(ordered_dates) - 1 - days)
        start_day = ordered_dates[start_index]
    base = close_at_window_start(segment.closes, start_day)
    if base is None or base <= 0:
        return None
    return (end_close / base - 1.0) * 100.0


async def build_sector_movers(
    registry,
    *,
    days: int,
    limit: int,
    market: Optional[str],
    min_cap_by_market: Optional[dict[str, float]] = None,
) -> SectorMoversResponse:
    min_cap_by_market = min_cap_by_market or {}
    requested_markets = [normalize_market_code(market)] if market else list(MARKETS)
    payload: dict[str, SectorMoversMarket] = {}

    sector_movers = registry.sector_precomputed_store.get_sector_movers_by_window(days)

    for internal_market in requested_markets:
        if internal_market is None:
            continue

        threshold = float(min_cap_by_market.get(internal_market) or 0.0)
        market_sectors = [s for s in sector_movers if s["market"] == internal_market and s["scope"] == "L3"]

        items: list[SectorItem] = []
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

            from dojoagents.dashboard.services.stock_sector_store import SectorBucketMeta

            meta = SectorBucketMeta(level="L3", zh=s["level3_id"], en=s["level3_id"])

            item = SectorItem(
                concept_code=concept_code_for(internal_market, meta),
                name=BilingualText(zh=s["level3_id"], en=s["level3_id"]),
                change_percent=round(s.get("daily_return_pct", 0), 2),
                avg_market_cap=(total_market_cap / s.get("member_count", 1)) if s.get("member_count") else 0.0,
                strength=0.0,
                sample_tickers=[m["ticker"] for m in top_by_abs],
                member_count=s.get("member_count", 0),
                members=sorted_members[:MAX_SECTOR_MEMBERS],
            )
            items.append(item)

        gainers = _apply_strength(sorted([item for item in items if item.change_percent > 0], key=lambda row: row.change_percent, reverse=True)[:limit])
        losers = _apply_strength(sorted([item for item in items if item.change_percent < 0], key=lambda row: row.change_percent)[:limit])
        native_market = to_native_market_code(internal_market) or internal_market
        payload[native_market] = SectorMoversMarket(
            market=native_market,
            days=days,
            gainers=gainers,
            losers=losers,
        )
    return SectorMoversResponse(days=days, markets=payload, as_of=None, source="computed", stale=False)


async def build_sector_analysis(
    registry,
    *,
    level1_id: str,
    level2_id: str,
    level3_id: str,
    scope: str,
) -> SectorAnalysisResponse:
    path = registry.sector_store.find_resolved_path(level1_id, level2_id, level3_id)
    if path is None:
        raise ValueError(f"unknown sector path: {level1_id}/{level2_id}/{level3_id}")

    async def compute_metrics_payload() -> dict[str, Any]:
        result = await compute_sector_scope_metrics(
            registry.stock_store,
            registry.stock_sector_store,
            path,
        )
        return result.model_dump()

    await registry.kline_store.prioritize_sector_path(path, market=None)
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
                registry.stock_sector_store,
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
        performance = cached_performance["payload"]
        scopes[current_scope] = SectorAnalysisScope(
            scope=current_scope,
            metrics=metrics,
            performance=performance,
        )
        if cached_performance.get("source"):
            sources.add(cached_performance["source"])
        stale = stale or bool(cached_performance.get("stale"))
    selected = scopes.get(scope) or scopes["L3"]
    return SectorAnalysisResponse(
        level1_id=level1_id,
        level2_id=level2_id,
        level3_id=level3_id,
        scope=selected.scope,
        scopes=scopes,
        as_of=selected.performance.get("as_of"),
        source="dashboard_cache" if sources == {"dashboard_cache"} else "computed",
        stale=stale,
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
        raise ValueError(f"unknown sector path: {level1_id}/{level2_id}/{level3_id}")
    window_start = None
    cached_scope = await registry.dojo_sphere_service.performance_cache.get(_sector_scope_cache_key(level1_id, level2_id, level3_id, scope))
    if cached_scope is not None:
        payload = cached_scope.get("payload") if isinstance(cached_scope, dict) else None
        if isinstance(payload, dict):
            window_start = payload.get("window_start")
    response = await list_sector_constituents(
        registry.stock_store,
        registry.stock_sector_store,
        registry.kline_store,
        registry.sector_precomputed_store,
        path,
        scope=scope,
        market=normalize_market_code(market),
        days=days,
        window_start=window_start,
    )
    native_market = to_native_market_code(response.market) if response.market else None
    items = [item.model_copy(update={"market": to_native_market_code(item.market) or item.market}) for item in response.items]
    return SectorConstituentsResponseV1(
        level1_id=response.level1_id,
        level2_id=response.level2_id,
        level3_id=response.level3_id,
        scope=response.scope,
        market=native_market,
        days=days,
        items=items,
        source="computed",
        stale=False,
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
    return TickerQuoteResponseV1(
        **quote.model_dump(),
        market=to_native_market_code(quote.market) or quote.market,
        name=_stock_bilingual_name(stock) if stock is not None else BilingualText(zh=quote.ticker, en=quote.ticker),
        sector_options=sector_response.sector_options if sector_response else [],
        source="sdk_online",
        stale=False,
    )


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
    return TickerFinancialsResponseV1(
        ticker=response.ticker,
        market=to_native_market_code(response.market) or response.market,
        report_type=report_type or response.report_type or report_type_for_market(internal_market),
        items=filtered,
        distributions=[item.model_dump() for item in income.distributions],
        report_date=income.report_date,
        as_of=response.as_of,
        source=response.source,
        stale=response.stale,
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
    return TickerNewsEventsResponseV1(
        ticker=ticker.strip().upper(),
        market=to_native_market_code(internal_market) or internal_market,
        news=FreshnessEnvelope(as_of=news.as_of, source=news.source, stale=news.stale),
        events=FreshnessEnvelope(as_of=events.as_of, source=events.source, stale=events.stale),
        news_items=news_items,
        event_items=event_items,
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
    return TickerPriceTrendsResponseV1(
        ticker=symbol,
        market=to_native_market_code(internal_market) or internal_market or "us",
        kline_t=kline_t,
        kline=FreshnessEnvelope(as_of=kline.as_of, source=kline.source, stale=kline.stale),
        pe_band=FreshnessEnvelope(as_of=pe_band.as_of if pe_band else None, source="computed", stale=False),
        bars=kline.bars,
        pe_points=[PeBandPoint(**point.model_dump()) for point in (pe_band.points if pe_band else [])],
    )


async def build_portfolio_list_v1(registry, *, query: Optional[str]) -> PortfolioListResponseV1:
    if query:
        search = await registry.portfolio_service.search(query)
        detail_map = {item.id: await registry.portfolio_service.get_detail(item.id, include_performance=False) for item in search.items}
        items = [detail for detail in detail_map.values() if detail is not None]
    else:
        items = await registry.portfolio_service.list_summaries()
    return PortfolioListResponseV1(items=items, source="local", stale=False)


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
    return PortfolioAnalysisResponseV1(detail=detail, source="local", stale=False)


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
