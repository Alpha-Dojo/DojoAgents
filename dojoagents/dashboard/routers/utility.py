from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from dojoagents.dashboard.deps import get_financial_registry
from dojoagents.dashboard.schemas.domain_api import CompanyTickerSearchResponse, TaxonomyTreeResponse
from dojoagents.dashboard.services.domain_api import build_taxonomy_tree, search_company_ticker

router = APIRouter(prefix="/utility", tags=["utility"])


@router.get("/search/company-ticker", response_model=CompanyTickerSearchResponse)
async def company_ticker_search(
    q: str = Query(..., min_length=1),
    market: Optional[str] = Query(None, pattern="^(cn|sh|hk|us)$"),
    limit: int = Query(20, ge=1, le=50),
    registry=Depends(get_financial_registry),
) -> CompanyTickerSearchResponse:
    return await search_company_ticker(registry, q=q, market=market, limit=limit)


@router.get("/taxonomy/tree", response_model=TaxonomyTreeResponse)
async def get_taxonomy_tree(
    registry=Depends(get_financial_registry),
) -> TaxonomyTreeResponse:
    return TaxonomyTreeResponse(taxonomy=build_taxonomy_tree(registry))
