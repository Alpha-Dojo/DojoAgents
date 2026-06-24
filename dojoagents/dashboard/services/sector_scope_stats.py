from __future__ import annotations

from typing import Dict, Any

from dojoagents.dashboard.services.market_stats import compute_market_stats
from dojoagents.dashboard.services.sector_constituents import MARKETS, SectorLevel, collect_sector_scope_tickers
from dojoagents.dashboard.services.sector_store import ResolvedSectorPath
from dojoagents.dashboard.services.stock_store import StockStore
from dojoagents.dashboard.schemas.dojo_sphere import SectorScopeMarketStats, SectorScopeMetricsResponse
from dojoagents.dashboard.schemas.market import MarketStats

LEVELS: tuple[SectorLevel, ...] = ("L1", "L2", "L3")


def _stats_for_tickers(
    stock_store: StockStore,
    market: str,
    tickers: set[str],
) -> MarketStats:
    if not tickers:
        return MarketStats(
            market=market,
            listed_count=0,
            total_market_cap=0.0,
            weighted_pe=None,
            simple_pe=None,
            pe_sample_count=0,
        )
    stocks = [stock for stock in stock_store.list_market(market) if stock.ticker in tickers]
    return compute_market_stats(market, stocks)


async def compute_sector_scope_metrics(
    stock_store: StockStore,
    sector_precomputed_store: Any,
    path: ResolvedSectorPath,
) -> SectorScopeMetricsResponse:
    """Total market cap and weighted PE for L1/L2/L3 scopes in each market."""
    scopes: Dict[SectorLevel, Dict[str, SectorScopeMarketStats]] = {level: {} for level in LEVELS}

    for market in MARKETS:
        grouped = collect_sector_scope_tickers(
            sector_precomputed_store,
            path,
            market=market,
        )
        for level in LEVELS:
            tickers = grouped.get(level) or set()
            stats = _stats_for_tickers(stock_store, market, tickers)
            scopes[level][market] = SectorScopeMarketStats(
                market=market,
                member_count=stats.listed_count,
                total_market_cap=stats.total_market_cap,
                weighted_pe=stats.weighted_pe,
                pe_sample_count=stats.pe_sample_count,
            )

    return SectorScopeMetricsResponse(
        level1_id=path.level1_id,
        level2_id=path.level2_id,
        level3_id=path.level3_id,
        scopes=scopes,
    )
