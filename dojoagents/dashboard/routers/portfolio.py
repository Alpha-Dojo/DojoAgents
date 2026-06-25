from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from dojoagents.dashboard.deps import get_financial_registry
from dojoagents.dashboard.schemas.domain_api import (
    AddPortfolioHoldingRequestV1,
    AddPortfolioHoldingsRequestV1,
    AutoAllocateRequestV1,
    ManagePortfolioRequestV1,
    PortfolioAnalysisResponseV1,
    PortfolioListResponseV1,
    RemovePortfolioHoldingRequestV1,
    UpdateHoldingsMetadataRequestV1,
)
from dojoagents.dashboard.schemas.portfolio import CreatePortfolioRequest, UpdatePortfolioRequest
from dojoagents.dashboard.services.domain_api import (
    build_portfolio_analysis_v1,
    build_portfolio_list_v1,
    build_update_request_from_manage,
    portfolio_detail_to_analysis,
)

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get(
    "",
    response_model=PortfolioListResponseV1,
    operation_id="list_or_search_portfolios",
    summary="List or search user portfolios",
)
async def portfolio_list(
    query: Optional[str] = Query(None, min_length=1),
    registry=Depends(get_financial_registry),
) -> PortfolioListResponseV1:
    return await build_portfolio_list_v1(registry, query=query)


@router.get(
    "/{portfolio_id}/analysis",
    response_model=PortfolioAnalysisResponseV1,
    operation_id="get_portfolio_analysis",
    summary="Holdings, NAV curve, and risk metrics for a portfolio",
)
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


@router.post(
    "/manage",
    response_model=PortfolioAnalysisResponseV1,
    operation_id="manage_portfolio",
    summary="Create, update, or delete a portfolio",
)
async def manage_portfolio(
    body: ManagePortfolioRequestV1,
    registry=Depends(get_financial_registry),
) -> PortfolioAnalysisResponseV1:
    if body.action == "create":
        if not body.name:
            raise HTTPException(status_code=400, detail="name is required for create")
        created = await registry.portfolio_service.create(CreatePortfolioRequest(name=body.name))
        return portfolio_detail_to_analysis(created)
    if not body.portfolio_id:
        raise HTTPException(status_code=400, detail="portfolio_id is required")
    if body.action == "update":
        detail = await registry.portfolio_service.update(
            body.portfolio_id,
            build_update_request_from_manage(body),
        )
        if detail is None:
            raise HTTPException(status_code=404, detail="portfolio not found")
        return portfolio_detail_to_analysis(detail)
    if body.action == "delete":
        ok = await registry.portfolio_service.delete(body.portfolio_id)
        if not ok:
            raise HTTPException(status_code=404, detail="portfolio not found")
        return PortfolioAnalysisResponseV1(id=body.portfolio_id, name=body.name or "")
    raise HTTPException(status_code=400, detail=f"unsupported action: {body.action}")


@router.post(
    "/holdings",
    response_model=PortfolioAnalysisResponseV1,
    operation_id="add_portfolio_holding",
    summary="Add a ticker to a portfolio",
)
async def add_holding(
    body: AddPortfolioHoldingRequestV1,
    registry=Depends(get_financial_registry),
) -> PortfolioAnalysisResponseV1:
    detail = await registry.portfolio_service.add_holding(
        body.portfolio_id,
        body.holding_details,
    )
    if detail is None:
        raise HTTPException(status_code=404, detail="portfolio or ticker not found")
    return portfolio_detail_to_analysis(detail)


@router.post(
    "/holdings/batch",
    response_model=PortfolioAnalysisResponseV1,
    operation_id="add_portfolio_holdings",
    summary="Add multiple tickers to a portfolio",
)
async def add_holdings_batch(
    body: AddPortfolioHoldingsRequestV1,
    registry=Depends(get_financial_registry),
) -> PortfolioAnalysisResponseV1:
    detail = None
    for holding in body.holdings:
        detail = await registry.portfolio_service.add_holding(body.portfolio_id, holding)
        if detail is None:
            raise HTTPException(status_code=404, detail="portfolio or ticker not found")
    if detail is None:
        raise HTTPException(status_code=400, detail="holdings are required")
    return portfolio_detail_to_analysis(detail)


@router.delete(
    "/holdings",
    response_model=PortfolioAnalysisResponseV1,
    operation_id="remove_portfolio_holding",
    summary="Remove a ticker from a portfolio",
)
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
    return portfolio_detail_to_analysis(detail)


@router.post(
    "/holdings/metadata",
    response_model=PortfolioAnalysisResponseV1,
    operation_id="update_portfolio_holdings_metadata",
    summary="Update per-holding open dates and share counts",
)
async def update_holdings_metadata(
    body: UpdateHoldingsMetadataRequestV1,
    registry=Depends(get_financial_registry),
) -> PortfolioAnalysisResponseV1:
    detail = await registry.portfolio_service.update(
        body.portfolio_id,
        UpdatePortfolioRequest(
            shares_by_ticker=body.shares_by_ticker,
            open_date_by_ticker=body.open_date_by_ticker,
        ),
    )
    if detail is None:
        raise HTTPException(status_code=404, detail="portfolio not found")
    return portfolio_detail_to_analysis(detail)


@router.post(
    "/allocate",
    response_model=PortfolioAnalysisResponseV1,
    operation_id="auto_allocate_portfolio",
    summary="Auto-assign weights by equal weight, market cap, or risk parity",
)
async def auto_allocate(
    body: AutoAllocateRequestV1,
    registry=Depends(get_financial_registry),
) -> PortfolioAnalysisResponseV1:
    detail = await registry.portfolio_service.auto_allocate(body.portfolio_id, body)
    if detail is None:
        raise HTTPException(status_code=404, detail="portfolio not found")
    return portfolio_detail_to_analysis(detail)
