from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from dojoagents.dashboard.deps import get_financial_registry
from dojoagents.dashboard.schemas.domain_api import (
    AddPortfolioHoldingRequestV1,
    AutoAllocateRequestV1,
    ManagePortfolioRequestV1,
    PortfolioAnalysisResponseV1,
    PortfolioListResponseV1,
    RemovePortfolioHoldingRequestV1,
)
from dojoagents.dashboard.schemas.portfolio import CreatePortfolioRequest
from dojoagents.dashboard.services.domain_api import (
    build_portfolio_analysis_v1,
    build_portfolio_list_v1,
    build_update_request_from_manage,
)

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("", response_model=PortfolioListResponseV1)
async def portfolio_list(
    query: Optional[str] = Query(None, min_length=1),
    registry=Depends(get_financial_registry),
) -> PortfolioListResponseV1:
    return await build_portfolio_list_v1(registry, query=query)


@router.get("/{portfolio_id}/analysis", response_model=PortfolioAnalysisResponseV1)
async def portfolio_analysis(
    portfolio_id: str,
    benchmark: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    include_performance: bool = Query(True),
    registry=Depends(get_financial_registry),
) -> PortfolioAnalysisResponseV1:
    detail = await build_portfolio_analysis_v1(
        registry,
        portfolio_id=portfolio_id,
        benchmark=benchmark,
        start_date=start_date,
        include_performance=include_performance,
    )
    if detail is None:
        raise HTTPException(status_code=404, detail="portfolio not found")
    return detail


@router.post("/manage", response_model=PortfolioAnalysisResponseV1)
async def manage_portfolio(
    body: ManagePortfolioRequestV1,
    registry=Depends(get_financial_registry),
) -> PortfolioAnalysisResponseV1:
    if body.action == "create":
        if not body.name:
            raise HTTPException(status_code=400, detail="name is required for create")
        created = await registry.portfolio_service.create(CreatePortfolioRequest(name=body.name))
        return PortfolioAnalysisResponseV1(detail=created, source="local", stale=False)
    if not body.portfolio_id:
        raise HTTPException(status_code=400, detail="portfolio_id is required")
    if body.action == "update":
        detail = await registry.portfolio_service.update(
            body.portfolio_id,
            build_update_request_from_manage(body),
        )
        if detail is None:
            raise HTTPException(status_code=404, detail="portfolio not found")
        return PortfolioAnalysisResponseV1(detail=detail, source="local", stale=False)
    if body.action == "delete":
        ok = await registry.portfolio_service.delete(body.portfolio_id)
        if not ok:
            raise HTTPException(status_code=404, detail="portfolio not found")
        return PortfolioAnalysisResponseV1(source="local", stale=False)
    raise HTTPException(status_code=400, detail=f"unsupported action: {body.action}")


@router.post("/holdings", response_model=PortfolioAnalysisResponseV1)
async def add_holding(
    body: AddPortfolioHoldingRequestV1,
    registry=Depends(get_financial_registry),
) -> PortfolioAnalysisResponseV1:
    detail = await registry.portfolio_service.add_holding(
        body.portfolio_id,
        body,
    )
    if detail is None:
        raise HTTPException(status_code=404, detail="portfolio or ticker not found")
    return PortfolioAnalysisResponseV1(detail=detail, source="local", stale=False)


@router.delete("/holdings", response_model=PortfolioAnalysisResponseV1)
async def remove_holding(
    body: RemovePortfolioHoldingRequestV1,
    registry=Depends(get_financial_registry),
) -> PortfolioAnalysisResponseV1:
    detail = await registry.portfolio_service.remove_holding(
        body.portfolio_id,
        body,
    )
    if detail is None:
        raise HTTPException(status_code=404, detail="portfolio or holding not found")
    return PortfolioAnalysisResponseV1(detail=detail, source="local", stale=False)


@router.post("/allocate", response_model=PortfolioAnalysisResponseV1)
async def auto_allocate(
    body: AutoAllocateRequestV1,
    registry=Depends(get_financial_registry),
) -> PortfolioAnalysisResponseV1:
    detail = await registry.portfolio_service.auto_allocate(body.portfolio_id, body)
    if detail is None:
        raise HTTPException(status_code=404, detail="portfolio not found")
    return PortfolioAnalysisResponseV1(detail=detail, source="local", stale=False)
