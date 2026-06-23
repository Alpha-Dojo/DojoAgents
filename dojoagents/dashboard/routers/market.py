from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from dojoagents.dashboard.deps import get_financial_registry
from dojoagents.dashboard.schemas.domain_api import MarketOverviewResponse, SectorMoversResponse
from dojoagents.dashboard.services.domain_api import build_market_overview, build_sector_movers

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/overview", response_model=MarketOverviewResponse)
async def market_overview(
    days: int = Query(1, ge=1, le=90),
    market: Optional[str] = Query(None, pattern="^(cn|sh|hk|us)$"),
    registry=Depends(get_financial_registry),
) -> MarketOverviewResponse:
    return await build_market_overview(registry, days=days, market=market)


@router.get("/sector-movers", response_model=SectorMoversResponse)
async def market_sector_movers(
    days: int = Query(1, ge=1, le=90),
    limit: int = Query(5, ge=1, le=20),
    market: Optional[str] = Query(None, pattern="^(cn|sh|hk|us)$"),
    min_cap_us: Optional[float] = Query(None, ge=0),
    min_cap_cn: Optional[float] = Query(None, ge=0),
    min_cap_hk: Optional[float] = Query(None, ge=0),
    registry=Depends(get_financial_registry),
) -> SectorMoversResponse:
    try:
        return await build_sector_movers(
            registry,
            days=days,
            limit=limit,
            market=market,
            min_cap_by_market={
                "us": min_cap_us or 0.0,
                "sh": min_cap_cn or 0.0,
                "hk": min_cap_hk or 0.0,
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
