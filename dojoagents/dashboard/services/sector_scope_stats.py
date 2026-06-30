from __future__ import annotations

import asyncio
from typing import Any, Dict

from dojoagents.dashboard.services.sector_constituents import MARKETS, SectorLevel
from dojoagents.dashboard.services.sector_store import ResolvedSectorPath
from dojoagents.dashboard.services.stock_store import StockStore
from dojoagents.dashboard.schemas.dojo_sphere import SectorScopeMarketStats, SectorScopeMetricsResponse

LEVELS: tuple[SectorLevel, ...] = ("L1", "L2", "L3")


def _empty_market_stats(market: str) -> SectorScopeMarketStats:
    return SectorScopeMarketStats(
        market=market,
        member_count=0,
        total_market_cap=0.0,
        weighted_pe=None,
        pe_sample_count=0,
    )


def _latest_sector_daily_stats(
    sector_precomputed_store: Any,
    path: ResolvedSectorPath,
    *,
    scope: SectorLevel,
    market: str,
) -> SectorScopeMarketStats:
    level2_id = path.level2_id if scope in ("L2", "L3") else ""
    level3_id = path.level3_id if scope == "L3" else ""
    rows = sector_precomputed_store.get_sector_daily(
        scope=scope,
        level1_id=path.level1_id,
        level2_id=level2_id,
        level3_id=level3_id,
        market=market,
    )
    if not rows:
        return _empty_market_stats(market)

    latest = max(rows, key=lambda row: str(row.get("trade_date") or ""))
    weighted_pe = latest.get("weighted_pe")
    return SectorScopeMarketStats(
        market=market,
        member_count=int(latest.get("member_count") or 0),
        total_market_cap=float(latest.get("total_market_cap") or 0.0),
        weighted_pe=float(weighted_pe) if weighted_pe is not None else None,
        pe_sample_count=0,
    )


async def compute_sector_scope_metrics(
    stock_store: StockStore,
    sector_precomputed_store: Any,
    path: ResolvedSectorPath,
) -> SectorScopeMetricsResponse:
    """Total market cap and weighted PE for L1/L2/L3 scopes in each market."""
    del stock_store
    return await asyncio.to_thread(
        _compute_sector_scope_metrics_sync,
        sector_precomputed_store,
        path,
    )


def _compute_sector_scope_metrics_sync(
    sector_precomputed_store: Any,
    path: ResolvedSectorPath,
) -> SectorScopeMetricsResponse:
    """Read latest precomputed sector_daily snapshot per scope and market."""
    scopes: Dict[SectorLevel, Dict[str, SectorScopeMarketStats]] = {level: {} for level in LEVELS}

    for market in MARKETS:
        for level in LEVELS:
            scopes[level][market] = _latest_sector_daily_stats(
                sector_precomputed_store,
                path,
                scope=level,
                market=market,
            )

    return SectorScopeMetricsResponse(
        level1_id=path.level1_id,
        level2_id=path.level2_id,
        level3_id=path.level3_id,
        scopes=scopes,
    )
