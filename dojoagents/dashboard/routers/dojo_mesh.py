from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from dojoagents.dashboard.deps import get_benchmark_store, get_sector_store, get_sector_precomputed_store
from dojoagents.dashboard.services.benchmark_store import BenchmarkStore
from dojoagents.dashboard.services.market_sector_lead import (
    compute_all_market_sector_leads,
    lookup_cross_market_sectors,
)
from dojoagents.dashboard.services.sector_store import SectorStore
from typing import Any
from dojoagents.dashboard.schemas.benchmark import DojoMeshBenchmarksResponse
from dojoagents.dashboard.schemas.dojo_mesh import CrossMarketSectorLookupResponse, DojoMeshSectorsResponse

router = APIRouter(prefix="/dojo-mesh", tags=["dojo-mesh"])


@router.get("/benchmarks", response_model=DojoMeshBenchmarksResponse)
async def list_benchmarks(
    store: BenchmarkStore = Depends(get_benchmark_store),
) -> DojoMeshBenchmarksResponse:
    """Cached benchmark klines for DojoMesh hero cards."""
    return await store.get_benchmarks()


@router.get("/sectors", response_model=DojoMeshSectorsResponse)
async def list_sectors(
    sector_limit: int = Query(5, ge=1, le=20),
    sector_store: SectorStore = Depends(get_sector_store),
    sector_precomputed_store: Any = Depends(get_sector_precomputed_store),
) -> DojoMeshSectorsResponse:
    """Level-3 sector gainers/losers from precomputed datasets."""
    return compute_all_market_sector_leads(
        sector_store,
        sector_precomputed_store,
        limit=sector_limit,
    )


@router.get("/sectors/cross-market", response_model=CrossMarketSectorLookupResponse)
async def lookup_sectors_cross_market(
    link_key: str = Query(..., min_length=1, description="Level-2 slug, e.g. cpu"),
    sector_store: SectorStore = Depends(get_sector_store),
    sector_precomputed_store: Any = Depends(get_sector_precomputed_store),
) -> CrossMarketSectorLookupResponse:
    """Resolve a level-2 sector across markets, even if not in top gainers/losers."""
    markets = lookup_cross_market_sectors(
        link_key,
        sector_store,
        sector_precomputed_store,
    )
    return CrossMarketSectorLookupResponse(link_key=link_key, markets=markets)
