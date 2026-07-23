from __future__ import annotations

from typing import Dict

from fastapi import APIRouter, Depends

from dojoagents.harnesses.built_in.financial.surfaces.dashboard_dependencies import get_stock_store
from dojoagents.harnesses.built_in.financial.services.stock_store import MARKETS, StockStore
from dojoagents.harnesses.built_in.financial.contracts.market import MarketStats

router = APIRouter(prefix="/markets", tags=["markets"])


@router.get("/stats", response_model=Dict[str, MarketStats])
async def list_market_stats(store: StockStore = Depends(get_stock_store)) -> Dict[str, MarketStats]:
    """Aggregate listed count, total cap, weighted/simple PE per market."""
    return store.all_market_stats()


@router.get("/{market}/stats", response_model=MarketStats)
async def get_market_stats(
    market: str,
    store: StockStore = Depends(get_stock_store),
) -> MarketStats:
    if market not in MARKETS:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"unknown market: {market}")
    return store.market_stats(market)
