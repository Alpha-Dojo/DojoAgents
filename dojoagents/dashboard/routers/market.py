from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from dojoagents.dashboard.deps import get_financial_registry
from dojoagents.dashboard.schemas.domain_api import (
    MarketOverviewResponse,
    SectorMoversResponse,
    StockScreenResponse,
)
from dojoagents.dashboard.services.domain_api import (
    build_market_overview,
    build_sector_movers,
    build_stock_screen,
)

router = APIRouter(prefix="/market", tags=["macro-market"])


@router.get(
    "/overview",
    response_model=MarketOverviewResponse,
    operation_id="get_market_overview",
    summary="Macro benchmark performance, total market cap, and weighted PE",
)
async def market_overview(
    days: int = Query(1, ge=1, le=90),
    market: Optional[str] = Query(None, pattern="^(cn|sh|hk|us)$"),
    registry=Depends(get_financial_registry),
) -> MarketOverviewResponse:
    return await build_market_overview(registry, days=days, market=market)


@router.get(
    "/sector-movers",
    response_model=SectorMoversResponse,
    operation_id="get_sector_movers",
    summary="Top gaining and losing L3 sectors by market-cap-weighted return",
)
async def market_sector_movers(
    days: int = Query(5, ge=0, le=90),
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


@router.get(
    "/screener",
    response_model=StockScreenResponse,
    operation_id="screen_market_stocks",
    summary="Screen quoted stocks; excludes delisted/zero-volume; default min cap ~10B; significance-weighted mover sort",
)
async def market_stock_screener(
    days: int = Query(0, ge=0, le=90),
    market: Optional[str] = Query(None, pattern="^(cn|sh|hk|us)$"),
    min_market_cap: Optional[float] = Query(None, ge=0),
    max_market_cap: Optional[float] = Query(None, ge=0),
    min_return_pct: Optional[float] = Query(None),
    max_return_pct: Optional[float] = Query(None),
    min_pe: Optional[float] = Query(None, ge=0),
    max_pe: Optional[float] = Query(None, ge=0),
    min_change_percent: Optional[float] = Query(None),
    max_change_percent: Optional[float] = Query(None),
    sort_by: str = Query("market_cap", pattern="^(market_cap|return_pct|change_percent|pe)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=100),
    registry=Depends(get_financial_registry),
) -> StockScreenResponse:
    try:
        return await build_stock_screen(
            registry,
            market=market,
            days=days,
            min_market_cap=min_market_cap,
            max_market_cap=max_market_cap,
            min_return_pct=min_return_pct,
            max_return_pct=max_return_pct,
            min_pe=min_pe,
            max_pe=max_pe,
            min_change_percent=min_change_percent,
            max_change_percent=max_change_percent,
            sort_by=sort_by,
            sort_order=sort_order,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
