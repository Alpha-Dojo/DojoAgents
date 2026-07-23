from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request

from dojoagents.harnesses.built_in.financial.surfaces.dashboard_dependencies import get_financial_registry
from dojoagents.harnesses.built_in.financial.contracts.domain_api import CompanyTickerSearchResponse, TaxonomyTreeResponse
from dojoagents.harnesses.built_in.financial.services.constituent_kline_refresh_state import RefreshStateStore
from dojoagents.harnesses.built_in.financial.services.domain_api import build_taxonomy_tree, search_company_ticker

router = APIRouter(prefix="/utility", tags=["utility-search"])


@router.get(
    "/market-data-revision",
    operation_id="get_market_data_revision",
    summary="Revision token for dashboard market/kline cache invalidation",
)
async def get_market_data_revision(
    request: Request,
) -> dict[str, str | None]:
    registry = getattr(request.app.state, "financial_registry", None)
    data_root = getattr(registry, "data_root", None) if registry is not None else None
    if data_root is None:
        return {"revision": "", "preload_date": None, "updated_at": None}
    store = RefreshStateStore(data_root / "runtime")
    return store.get_market_data_revision()


@router.get(
    "/search/company-ticker",
    response_model=CompanyTickerSearchResponse,
    operation_id="search_company_ticker",
    summary="Resolve company name or ticker to market codes",
)
async def company_ticker_search(
    q: str = Query(..., min_length=1, description="Company name (zh/en) or ticker symbol"),
    market: Optional[str] = Query(None, pattern="^(cn|sh|hk|us)$"),
    limit: int = Query(20, ge=1, le=50),
    registry=Depends(get_financial_registry),
) -> CompanyTickerSearchResponse:
    return await search_company_ticker(registry, q=q, market=market, limit=limit)


@router.get(
    "/taxonomy/tree",
    response_model=TaxonomyTreeResponse,
    operation_id="get_taxonomy_tree",
    summary="Full L1-L2-L3 sector taxonomy for drill-down navigation",
)
async def get_taxonomy_tree(
    registry=Depends(get_financial_registry),
) -> TaxonomyTreeResponse:
    return TaxonomyTreeResponse(**build_taxonomy_tree(registry))
