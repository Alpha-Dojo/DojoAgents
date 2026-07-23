from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from dojoagents.harnesses.built_in.financial.surfaces.dashboard_dependencies import get_portfolio_service
from dojoagents.harnesses.built_in.financial.services.portfolio_service import PortfolioService
from dojoagents.harnesses.built_in.financial.services.portfolio_service import PortfolioValidationError
from dojoagents.harnesses.built_in.financial.contracts.portfolio import (
    AddPortfolioHoldingRequest,
    AutoAllocateRequest,
    CreatePortfolioRequest,
    PortfolioDetail,
    PortfolioSearchResponse,
    PortfolioSummary,
    UpdatePortfolioRequest,
)

router = APIRouter(prefix="/dojo-folio", tags=["dojo-folio"])


@router.get("/portfolios", response_model=list[PortfolioSummary])
async def list_portfolios(
    service: PortfolioService = Depends(get_portfolio_service),
) -> list[PortfolioSummary]:
    return await service.list_summaries()


@router.get("/portfolios/search", response_model=PortfolioSearchResponse)
async def search_portfolios(
    q: str = Query(..., min_length=1),
    service: PortfolioService = Depends(get_portfolio_service),
) -> PortfolioSearchResponse:
    return await service.search(q)


@router.get("/portfolios/{portfolio_id}", response_model=PortfolioDetail)
async def get_portfolio(
    portfolio_id: str,
    include_performance: bool = Query(True),
    benchmark_us: str = Query("^SPX"),
    benchmark_sh: str = Query("000001.SS"),
    benchmark_hk: str = Query("^HSI"),
    service: PortfolioService = Depends(get_portfolio_service),
) -> PortfolioDetail:
    detail = await service.get_detail(
        portfolio_id,
        include_performance=include_performance,
        benchmark_by_market={
            "us": benchmark_us,
            "sh": benchmark_sh,
            "hk": benchmark_hk,
        },
    )
    if detail is None:
        raise HTTPException(status_code=404, detail="portfolio not found")
    return detail


@router.post("/portfolios", response_model=PortfolioDetail, status_code=201)
async def create_portfolio(
    body: CreatePortfolioRequest,
    service: PortfolioService = Depends(get_portfolio_service),
) -> PortfolioDetail:
    return await service.create(body)


@router.patch("/portfolios/{portfolio_id}", response_model=PortfolioDetail)
async def update_portfolio(
    portfolio_id: str,
    body: UpdatePortfolioRequest,
    service: PortfolioService = Depends(get_portfolio_service),
) -> PortfolioDetail:
    try:
        detail = await service.update(portfolio_id, body)
    except PortfolioValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "message": str(exc),
                "field": exc.field,
                "context": exc.context,
            },
        ) from exc
    if detail is None:
        raise HTTPException(status_code=404, detail="portfolio not found")
    return detail


@router.delete("/portfolios/{portfolio_id}", status_code=204, response_model=None)
async def delete_portfolio(
    portfolio_id: str,
    service: PortfolioService = Depends(get_portfolio_service),
) -> Response:
    if not await service.delete(portfolio_id):
        raise HTTPException(status_code=404, detail="portfolio not found")
    return Response(status_code=204)


@router.post("/portfolios/{portfolio_id}/holdings", response_model=PortfolioDetail)
async def add_portfolio_holding(
    portfolio_id: str,
    body: AddPortfolioHoldingRequest,
    service: PortfolioService = Depends(get_portfolio_service),
) -> PortfolioDetail:
    detail = await service.add_holding(portfolio_id, body)
    if detail is None:
        raise HTTPException(status_code=404, detail="portfolio or ticker not found")
    return detail


@router.post("/portfolios/{portfolio_id}/allocate", response_model=PortfolioDetail)
async def auto_allocate_portfolio(
    portfolio_id: str,
    body: AutoAllocateRequest,
    service: PortfolioService = Depends(get_portfolio_service),
) -> PortfolioDetail:
    detail = await service.auto_allocate(portfolio_id, body)
    if detail is None:
        raise HTTPException(status_code=404, detail="portfolio not found")
    return detail
