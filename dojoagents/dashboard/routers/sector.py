from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from dojoagents.dashboard.deps import get_financial_registry
from dojoagents.dashboard.schemas.domain_api import SectorAnalysisResponse, SectorConstituentsResponseV1
from dojoagents.dashboard.services.domain_api import (
    build_sector_analysis,
    build_sector_constituents_v1,
    resolve_sector_analysis_path,
)

router = APIRouter(prefix="/sector", tags=["sector-analysis"])


@router.get(
    "/analysis",
    response_model=SectorAnalysisResponse,
    operation_id="get_sector_analysis",
    summary="Sector market cap, weighted PE, NAV curves, and risk stats",
)
async def sector_analysis(
    level1_id: str = Query(..., min_length=1),
    level2_id: str = Query(..., min_length=1),
    level3_id: str = Query(..., min_length=1),
    scope: Literal["L1", "L2", "L3"] = Query("L3"),
    registry=Depends(get_financial_registry),
) -> SectorAnalysisResponse:
    path = resolve_sector_analysis_path(
        registry,
        level1_id=level1_id,
        level2_id=level2_id,
        level3_id=level3_id,
    )
    if path is None:
        raise HTTPException(
            status_code=404,
            detail=f"unknown sector path: {level1_id}/{level2_id}/{level3_id}",
        )
    return await build_sector_analysis(registry, path, scope=scope)


@router.get(
    "/constituents",
    response_model=SectorConstituentsResponseV1,
    operation_id="filter_sector_constituents",
    summary="All constituents in a sector with quote and valuation metrics",
)
async def sector_constituents(
    level1_id: str = Query(..., min_length=1),
    level2_id: str = Query(..., min_length=1),
    level3_id: str = Query(..., min_length=1),
    market: Optional[str] = Query(None, pattern="^(cn|sh|hk|us)$"),
    scope: Literal["L1", "L2", "L3"] = Query("L3"),
    days: int = Query(1, ge=1, le=90),
    registry=Depends(get_financial_registry),
) -> SectorConstituentsResponseV1:
    try:
        return await build_sector_constituents_v1(
            registry,
            level1_id=level1_id,
            level2_id=level2_id,
            level3_id=level3_id,
            scope=scope,
            market=market,
            days=days,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
