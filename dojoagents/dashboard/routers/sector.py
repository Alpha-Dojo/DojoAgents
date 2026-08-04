from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from dojoagents.dashboard.deps import get_financial_registry
from dojoagents.dashboard.schemas.domain_api import (
    SectorAnalysisResponse,
    SectorAttributionFactorsResponse,
    SectorConstituentsResponseV1,
)
from dojoagents.dashboard.services.attribution_factor_service import (
    build_sector_attribution_factors,
)
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
    start_date: Optional[str] = Query(None, description="Optional window start YYYY-MM-DD; requires end_date"),
    end_date: Optional[str] = Query(None, description="Optional window end YYYY-MM-DD; requires start_date"),
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
            start_date=start_date,
            end_date=end_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/attribution-factors",
    response_model=SectorAttributionFactorsResponse,
    operation_id="get_sector_attribution_factors",
    summary="Sector attribution factors in a date window (exact sector_id + event_time filter)",
)
async def sector_attribution_factors(
    market: str = Query(..., pattern="^(cn|sh|hk|us)$"),
    start_date: str = Query(..., description="Inclusive lower bound YYYY-MM-DD (event_time calendar day)"),
    end_date: str = Query(..., description="Inclusive upper bound YYYY-MM-DD (event_time calendar day)"),
    sector_id: Optional[str] = Query(
        None,
        description="Exact L1/L2/L3 path; alternative to level1_id/level2_id/level3_id",
    ),
    level1_id: Optional[str] = Query(None, min_length=1),
    level2_id: Optional[str] = Query(None, min_length=1),
    level3_id: Optional[str] = Query(None, min_length=1),
    locale: Literal["zh", "en"] = Query("zh"),
    limit: Optional[int] = Query(None, ge=1, le=1000, description="Optional post-filter safety cap"),
    registry=Depends(get_financial_registry),
) -> SectorAttributionFactorsResponse:
    resolved = (sector_id or "").strip()
    if not resolved:
        if level1_id and level2_id and level3_id:
            resolved = f"{level1_id.strip()}/{level2_id.strip()}/{level3_id.strip()}"
        else:
            raise HTTPException(
                status_code=400,
                detail="Provide sector_id or level1_id/level2_id/level3_id",
            )
    client = registry.client
    if client is None:
        raise HTTPException(status_code=503, detail="Dojo client is not initialized")
    try:
        return await build_sector_attribution_factors(
            client,
            market=market,
            sector_id=resolved,
            start_date=start_date,
            end_date=end_date,
            locale=locale,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to load attribution factors: {exc}",
        ) from exc
