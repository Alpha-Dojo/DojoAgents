from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from dojoagents.harnesses.built_in.financial.surfaces.dashboard_dependencies import get_financial_registry
from dojoagents.harnesses.built_in.financial.contracts.domain_api import (
    MarketDynamicsResponse,
    MarketOverviewResponse,
    SectorMoversResponse,
    StockScreenResponse,
)
from dojoagents.harnesses.built_in.financial.services.domain_api import (
    build_market_overview,
    build_sector_movers,
    build_stock_screen,
)
from dojoagents.harnesses.built_in.financial.services.market_dynamics_service import build_market_dynamics

router = APIRouter(prefix="/market", tags=["macro-market"])


@router.get(
    "/overview",
    response_model=MarketOverviewResponse,
    operation_id="get_market_overview",
    summary="Macro benchmark performance, total market cap, and weighted PE",
)
async def market_overview(
    days: int = Query(1, ge=0, le=90),
    market: Optional[str] = Query(None, pattern="^(cn|sh|hk|us)$"),
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD, requires end_date"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD, requires start_date"),
    registry=Depends(get_financial_registry),
) -> MarketOverviewResponse:
    try:
        return await build_market_overview(
            registry,
            days=days,
            market=market,
            start_date=start_date,
            end_date=end_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD, requires end_date"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD, requires start_date"),
    min_cap_us: Optional[float] = Query(None, ge=0),
    min_cap_cn: Optional[float] = Query(None, ge=0),
    min_cap_hk: Optional[float] = Query(None, ge=0),
    include_members: bool = Query(
        True,
        description="Include top_members / sample tickers (false for treemap/discovery)",
    ),
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
            start_date=start_date,
            end_date=end_date,
            include_members=include_members,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/dynamics",
    response_model=MarketDynamicsResponse,
    operation_id="get_market_dynamics",
    summary="Cross-market event timeline from Dojo analysis.market_dynamics",
)
async def market_dynamics(
    limit: int = Query(5000, ge=1, le=10000),
    start_date: Optional[str] = Query(
        None,
        description="YYYY-MM-DD inclusive lower bound (filtered server-side)",
    ),
    end_date: Optional[str] = Query(
        None,
        description="YYYY-MM-DD inclusive upper bound (filtered server-side)",
    ),
    registry=Depends(get_financial_registry),
) -> MarketDynamicsResponse:
    client = registry.client
    if client is None:
        raise HTTPException(status_code=503, detail="Dojo client is not initialized")
    if (start_date and not end_date) or (end_date and not start_date):
        raise HTTPException(
            status_code=400,
            detail="start_date and end_date must be provided together",
        )
    try:
        return await build_market_dynamics(
            client,
            limit=limit,
            start_date=start_date,
            end_date=end_date,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to load market dynamics: {exc}") from exc


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
