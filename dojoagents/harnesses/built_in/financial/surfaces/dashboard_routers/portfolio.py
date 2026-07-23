from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from dojoagents.harnesses.built_in.financial.surfaces.dashboard_dependencies import get_financial_registry
from dojoagents.harnesses.built_in.financial.contracts.domain_api import (
    AddPortfolioHoldingRequestV1,
    AddPortfolioHoldingsRequestV1,
    AutoAllocateRequestV1,
    CancelPortfolioOrderRequestV1,
    CreatePortfolioOrderRequestV1,
    ManagePortfolioRequestV1,
    PortfolioAnalysisResponseV1,
    PortfolioListResponseV1,
    PortfolioPerformanceResponseV1,
    RemovePortfolioHoldingRequestV1,
    RemovePortfolioHoldingsRequestV1,
    SyncPortfolioPositionsRequestV1,
    UpdateHoldingsMetadataRequestV1,
)
from dojoagents.harnesses.built_in.financial.contracts.portfolio import (
    CancelPortfolioOrderRequest,
    CreatePortfolioOrderRequest,
    CreatePortfolioRequest,
    PositionSyncItem,
    RemovePortfolioHoldingRequest,
    SyncPortfolioPositionsRequest,
    UpdatePortfolioRequest,
)
from dojoagents.harnesses.built_in.financial.services.domain_api import (
    build_portfolio_analysis_v1,
    build_portfolio_list_v1,
    build_portfolio_performance_v1,
    build_portfolio_summary_v1,
    build_update_request_from_manage,
    portfolio_detail_to_analysis,
)
from dojoagents.harnesses.built_in.financial.services.portfolio_service import PortfolioOrderFillError, PortfolioValidationError

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
    "/{portfolio_id}/analysis/summary",
    response_model=PortfolioAnalysisResponseV1,
    operation_id="get_portfolio_analysis_summary",
    summary="Holdings and quotes for a portfolio without NAV performance",
)
async def portfolio_analysis_summary(
    portfolio_id: str,
    start_date: Optional[str] = Query(None),
    registry=Depends(get_financial_registry),
) -> PortfolioAnalysisResponseV1:
    detail = await build_portfolio_summary_v1(
        registry,
        portfolio_id=portfolio_id,
        start_date=start_date,
    )
    if detail is None:
        raise HTTPException(status_code=404, detail="portfolio not found")
    return detail


@router.get(
    "/{portfolio_id}/analysis/performance",
    response_model=PortfolioPerformanceResponseV1,
    operation_id="get_portfolio_analysis_performance",
    summary="NAV curve and risk metrics for a portfolio",
)
async def portfolio_analysis_performance(
    portfolio_id: str,
    benchmark: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    registry=Depends(get_financial_registry),
) -> PortfolioPerformanceResponseV1:
    detail = await build_portfolio_performance_v1(
        registry,
        portfolio_id=portfolio_id,
        benchmark=benchmark,
        start_date=start_date,
    )
    if detail is None:
        raise HTTPException(status_code=404, detail="portfolio not found")
    return detail


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
        created = await registry.portfolio_service.create(
            CreatePortfolioRequest(name=body.name, kind=body.kind or "manual"),
        )
        return portfolio_detail_to_analysis(created)
    if not body.portfolio_id:
        raise HTTPException(status_code=400, detail="portfolio_id is required")
    if body.action == "update":
        try:
            detail = await registry.portfolio_service.update(
                body.portfolio_id,
                build_update_request_from_manage(body),
            )
        except PortfolioValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
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
    detail = await registry.portfolio_service.add_holdings_batch(
        body.portfolio_id,
        [holding for holding in body.holdings],
    )
    if detail is None:
        raise HTTPException(status_code=404, detail="portfolio or ticker not found")
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


@router.delete(
    "/holdings/batch",
    response_model=PortfolioAnalysisResponseV1,
    operation_id="remove_portfolio_holdings",
    summary="Remove multiple tickers from a portfolio watchlist",
)
async def remove_holdings_batch(
    body: RemovePortfolioHoldingsRequestV1,
    registry=Depends(get_financial_registry),
) -> PortfolioAnalysisResponseV1:
    bodies = [
        RemovePortfolioHoldingRequest(
            ticker=holding.ticker,
            market=holding.market,
        )
        for holding in body.holdings
    ]
    detail, _blocked = await registry.portfolio_service.remove_holdings_batch(
        body.portfolio_id,
        bodies,
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


@router.post(
    "/orders",
    response_model=PortfolioAnalysisResponseV1,
    operation_id="create_portfolio_order",
    summary="Place a buy/sell order for a portfolio position",
)
async def create_order(
    body: CreatePortfolioOrderRequestV1,
    registry=Depends(get_financial_registry),
) -> PortfolioAnalysisResponseV1:
    try:
        detail = await registry.portfolio_service.create_order(
            body.portfolio_id,
            CreatePortfolioOrderRequest(
                ticker=body.ticker,
                market=body.market,
                order_side=body.order_side,
                price=body.price,
                qty=body.qty,
                order_time=body.order_time,
            ),
        )
    except PortfolioOrderFillError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "message": str(exc),
                "code": exc.code,
                "order_id": exc.order_id,
                "context": exc.context,
            },
        ) from exc
    if detail is None:
        raise HTTPException(status_code=404, detail="portfolio or ticker not found")
    return portfolio_detail_to_analysis(detail)


@router.post(
    "/position-sync",
    response_model=PortfolioAnalysisResponseV1,
    operation_id="sync_portfolio_positions",
    summary="Sync absolute positions from an external account",
)
async def sync_positions(
    body: SyncPortfolioPositionsRequestV1,
    registry=Depends(get_financial_registry),
) -> PortfolioAnalysisResponseV1:
    try:
        detail = await registry.portfolio_service.sync_positions(
            body.portfolio_id,
            SyncPortfolioPositionsRequest(
                items=[
                    PositionSyncItem(
                        ticker=item.ticker,
                        market=item.market,
                        qty=item.qty,
                        cost=item.cost,
                    )
                    for item in body.items
                ],
                synced_at=body.synced_at,
                source=body.source,
                note=body.note,
            ),
        )
    except PortfolioValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "field": exc.field, "context": exc.context or {}},
        ) from exc
    if detail is None:
        raise HTTPException(status_code=404, detail="portfolio not found")
    return portfolio_detail_to_analysis(detail)


@router.delete(
    "/orders",
    response_model=PortfolioAnalysisResponseV1,
    operation_id="cancel_portfolio_order",
    summary="Cancel a pending portfolio order",
)
async def cancel_order(
    body: CancelPortfolioOrderRequestV1,
    registry=Depends(get_financial_registry),
) -> PortfolioAnalysisResponseV1:
    detail = await registry.portfolio_service.cancel_order(
        body.portfolio_id,
        CancelPortfolioOrderRequest(order_id=body.order_id),
    )
    if detail is None:
        raise HTTPException(status_code=404, detail="portfolio or order not found")
    return portfolio_detail_to_analysis(detail)
