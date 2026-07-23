from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from dojoagents.dashboard.deps import (
    get_kline_store,
    get_sector_store,
    get_sector_precomputed_store,
    get_stock_store,
    get_dojo_sphere_service,
)
from dojoagents.dashboard.services.kline_store import KlineStore
from dojoagents.dashboard.services.sector_constituents_list import list_sector_constituents
from dojoagents.dashboard.services.sector_scope_performance import compute_sector_scope_performance
from dojoagents.dashboard.services.sector_scope_stats import compute_sector_scope_metrics
from dojoagents.dashboard.services.sector_store import SectorStore
from dojoagents.dashboard.services.stock_store import StockStore
from dojoagents.dashboard.services.dojo_sphere_service import DojoSphereService
from dojoagents.dashboard.schemas.dojo_sphere import (
    SectorConstituentsResponse,
    SectorPerformanceResponse,
    SectorScopeMetricsResponse,
)
from dojoagents.dashboard.schemas.stock_kline import (
    ConstituentKlineBatchResponse,
    ConstituentKlineStatsResponse,
    SectorConstituentKlineResponse,
    StockKlineResponse,
)

router = APIRouter(prefix="/dojo-sphere", tags=["dojo-sphere"])


@router.get("/sectors/metrics", response_model=SectorScopeMetricsResponse)
async def sector_scope_metrics(
    level1_id: str = Query(..., min_length=1),
    level2_id: str = Query(..., min_length=1),
    level3_id: str = Query(..., min_length=1),
    sector_store: SectorStore = Depends(get_sector_store),
    stock_store: StockStore = Depends(get_stock_store),
    sector_precomputed_store: Any = Depends(get_sector_precomputed_store),
    sphere_service: DojoSphereService = Depends(get_dojo_sphere_service),
) -> SectorScopeMetricsResponse:
    """L1/L2/L3 total market cap and weighted PE by market (us, sh, hk)."""
    path = sector_store.find_resolved_path(level1_id, level2_id, level3_id)
    if path is None:
        raise HTTPException(
            status_code=404,
            detail=f"unknown sector path: {level1_id}/{level2_id}/{level3_id}",
        )

    async def compute() -> dict:
        result = await compute_sector_scope_metrics(stock_store, sector_precomputed_store, path)
        return result.model_dump()

    cached = await sphere_service.metrics(f"{level1_id}/{level2_id}/{level3_id}", compute)
    return SectorScopeMetricsResponse.model_validate(cached)


@router.get("/sectors/constituents", response_model=SectorConstituentsResponse)
async def sector_constituents(
    level1_id: str = Query(..., min_length=1),
    level2_id: str = Query(..., min_length=1),
    level3_id: str = Query(..., min_length=1),
    market: Optional[str] = Query(
        None,
        description="Optional market filter: sh, hk, or us",
        pattern="^(sh|hk|us)$",
    ),
    scope: Literal["L1", "L2", "L3"] = Query(
        "L3",
        description="Constituent scope level: L1, L2, or L3",
    ),
    sector_store: SectorStore = Depends(get_sector_store),
    stock_store: StockStore = Depends(get_stock_store),
    sector_precomputed_store: Any = Depends(get_sector_precomputed_store),
) -> SectorConstituentsResponse:
    """L1/L2/L3 constituent rows from stock profile and quote."""
    path = sector_store.find_resolved_path(level1_id, level2_id, level3_id)
    if path is None:
        raise HTTPException(
            status_code=404,
            detail=f"unknown sector path: {level1_id}/{level2_id}/{level3_id}",
        )
    return await list_sector_constituents(
        stock_store,
        sector_precomputed_store,
        path,
        scope=scope,
        market=market,
    )


@router.get("/sectors/performance", response_model=SectorPerformanceResponse)
async def sector_scope_performance(
    level1_id: str = Query(..., min_length=1),
    level2_id: str = Query(..., min_length=1),
    level3_id: str = Query(..., min_length=1),
    scope: Literal["L1", "L2", "L3"] = Query(
        "L3",
        description="Constituent scope level: L1, L2, or L3",
    ),
    sector_store: SectorStore = Depends(get_sector_store),
    stock_store: StockStore = Depends(get_stock_store),
    kline_store: KlineStore = Depends(get_kline_store),
    sector_precomputed_store: Any = Depends(get_sector_precomputed_store),
    sphere_service: DojoSphereService = Depends(get_dojo_sphere_service),
) -> SectorPerformanceResponse:
    """Earnings-weighted sector index curves by market (us, sh, hk)."""
    path = sector_store.find_resolved_path(level1_id, level2_id, level3_id)
    if path is None:
        raise HTTPException(
            status_code=404,
            detail=f"unknown sector path: {level1_id}/{level2_id}/{level3_id}",
        )

    async def compute() -> dict:
        result = await compute_sector_scope_performance(
            stock_store,
            kline_store,
            sector_precomputed_store,
            path,
            scope=scope,
        )
        return result.model_dump()

    cached = await sphere_service.performance(f"{scope}/{level1_id}/{level2_id}/{level3_id}", compute)
    return SectorPerformanceResponse.model_validate(
        {
            **cached["payload"],
            "as_of": cached.get("as_of"),
            "source": cached.get("source", "computed"),
            "stale": cached.get("stale", False),
        }
    )


@router.get("/constituents/kline/stats", response_model=ConstituentKlineStatsResponse)
async def constituent_kline_stats(
    store: KlineStore = Depends(get_kline_store),
) -> ConstituentKlineStatsResponse:
    """Cache health for DojoMesh constituent klines."""
    return await store.stats()


@router.get("/sectors/kline", response_model=SectorConstituentKlineResponse)
async def sector_constituent_klines(
    level1_id: str = Query(..., min_length=1, description="Level-1 sector id from cached sector tree"),
    level2_id: str = Query(..., min_length=1, description="Level-2 sector id from cached sector tree"),
    level3_id: str = Query(..., min_length=1, description="Level-3 sector id from cached sector tree"),
    market: Optional[str] = Query(
        None,
        description="Optional market filter: sh, hk, or us",
        pattern="^(sh|hk|us)$",
    ),
    store: KlineStore = Depends(get_kline_store),
    sector_store: SectorStore = Depends(get_sector_store),
) -> SectorConstituentKlineResponse:
    """
    Return cached constituent klines grouped by sector level (L3 → L2 → L1).

    Sector ids come from the in-memory sector tree loaded via query_sector_info.
    Triggers prioritized upstream fetch: L3 constituents first, then L2-only, then L1-only.
    """
    path = sector_store.find_resolved_path(level1_id, level2_id, level3_id)
    if path is None:
        raise HTTPException(
            status_code=404,
            detail=f"unknown sector path: {level1_id}/{level2_id}/{level3_id}",
        )

    return await store.get_sector_klines(path, market=market)


@router.get("/constituents/kline", response_model=ConstituentKlineBatchResponse)
async def batch_constituent_klines(
    symbols: str = Query(..., min_length=1, description="Comma-separated tickers"),
    store: KlineStore = Depends(get_kline_store),
) -> ConstituentKlineBatchResponse:
    """Fetch cached daily klines for explicit tickers (prefer /sectors/kline for DojoSphere)."""
    requested = [item.strip() for item in symbols.split(",") if item.strip()]
    if not requested:
        raise HTTPException(status_code=400, detail="symbols is required")
    if len(requested) > 100:
        raise HTTPException(status_code=400, detail="too many symbols (max 100)")
    return await store.get_klines(requested)


@router.get("/constituents/{symbol}/kline", response_model=StockKlineResponse)
async def get_constituent_kline(
    symbol: str,
    store: KlineStore = Depends(get_kline_store),
) -> StockKlineResponse:
    """Fetch cached 252-day daily kline for one DojoMesh constituent ticker."""
    response = await store.get_kline(symbol)
    if response is None:
        raise HTTPException(status_code=404, detail=f"kline not found for {symbol}")
    return response
