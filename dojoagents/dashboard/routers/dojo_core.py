from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from dojoagents.dashboard.deps import (
    get_kline_store,
    get_sector_store,
    get_stock_event_store,
    get_stock_fin_indicators_store,
    get_stock_income_store,
    get_stock_news_store,
    get_stock_sector_store,
    get_stock_store,
)
from dojoagents.dashboard.services.kline_store import KlineStore
from dojoagents.dashboard.services.dojo_core_search import search_core_tickers
from dojoagents.dashboard.services.dojo_core_pe import resolve_core_ticker_pe_band
from dojoagents.dashboard.services.dojo_core_quote import resolve_core_ticker_quote
from dojoagents.dashboard.services.dojo_core_sector import resolve_core_ticker_sector
from dojoagents.dashboard.services.sector_store import SectorStore
from dojoagents.dashboard.services.stock_fin_indicators_store import StockFinIndicatorsStore
from dojoagents.dashboard.services.stock_event_store import StockEventStore
from dojoagents.dashboard.services.stock_income_store import StockIncomeStore
from dojoagents.dashboard.services.stock_news_store import StockNewsStore
from dojoagents.dashboard.services.stock_sector_store import StockSectorStore
from dojoagents.dashboard.services.stock_store import StockStore
from dojoagents.dashboard.schemas.dojo_core import (
    CoreTickerPeBandResponse,
    CoreTickerQuoteResponse,
    CoreTickerSearchResponse,
    CoreTickerSectorResponse,
)
from dojoagents.dashboard.schemas.stock_fin_indicators import CoreTickerFinIndicatorsResponse
from dojoagents.dashboard.schemas.stock_event import CoreTickerEventsResponse
from dojoagents.dashboard.schemas.stock_income import CoreTickerIncomeResponse
from dojoagents.dashboard.schemas.stock_news import CoreTickerNewsResponse
from dojoagents.dashboard.schemas.stock_kline import StockKlineResponse

router = APIRouter(prefix="/dojo-core", tags=["dojo-core"])


@router.get("/tickers/search", response_model=CoreTickerSearchResponse)
async def search_tickers(
    q: str = Query(..., min_length=1, description="Ticker symbol or company name"),
    market: Optional[str] = Query(
        None,
        description="Optional market filter: sh, hk, or us",
        pattern="^(sh|hk|us)$",
    ),
    level1_id: Optional[str] = Query(None, min_length=1),
    level2_id: Optional[str] = Query(None, min_length=1),
    level3_id: Optional[str] = Query(None, min_length=1),
    limit: int = Query(20, ge=1, le=50),
    stock_store: StockStore = Depends(get_stock_store),
    stock_sector_store: StockSectorStore = Depends(get_stock_sector_store),
    sector_store: SectorStore = Depends(get_sector_store),
) -> CoreTickerSearchResponse:
    """Search quoted tickers by ticker symbol or company name (zh/en), across all markets."""
    items = search_core_tickers(
        stock_store,
        stock_sector_store,
        sector_store,
        q,
        market=market,
        level1_id=level1_id,
        level2_id=level2_id,
        level3_id=level3_id,
        limit=limit,
    )
    return CoreTickerSearchResponse(query=q.strip(), items=items)


@router.get("/ticker/sector", response_model=CoreTickerSectorResponse)
async def get_ticker_sector(
    ticker: str = Query(..., min_length=1, description="Stock ticker"),
    market: Optional[str] = Query(
        None,
        description="Optional market code: sh, hk, or us",
        pattern="^(sh|hk|us)$",
    ),
    stock_store: StockStore = Depends(get_stock_store),
    stock_sector_store: StockSectorStore = Depends(get_stock_sector_store),
    sector_store: SectorStore = Depends(get_sector_store),
) -> CoreTickerSectorResponse:
    """Primary L1/L2/L3 sector path for a DojoCore ticker."""
    response = resolve_core_ticker_sector(
        ticker,
        market=market,
        stock_store=stock_store,
        stock_sector_store=stock_sector_store,
        sector_store=sector_store,
    )
    if response is None:
        raise HTTPException(status_code=404, detail=f"sector path not found for {ticker}")
    return response


@router.get("/ticker/quote", response_model=CoreTickerQuoteResponse)
async def get_ticker_quote(
    ticker: str = Query(..., min_length=1, description="Stock ticker"),
    market: Optional[str] = Query(
        None,
        description="Optional market code: sh, hk, or us",
        pattern="^(sh|hk|us)$",
    ),
    stock_store: StockStore = Depends(get_stock_store),
) -> CoreTickerQuoteResponse:
    """Latest quote for a DojoCore ticker (from in-memory stock store)."""
    response = resolve_core_ticker_quote(ticker, market=market, stock_store=stock_store)
    if response is None:
        raise HTTPException(status_code=404, detail=f"quote not found for {ticker}")
    return response


@router.get("/ticker/fin-indicators", response_model=CoreTickerFinIndicatorsResponse)
async def get_ticker_fin_indicators(
    ticker: str = Query(..., min_length=1, description="Stock ticker"),
    market: Optional[str] = Query(
        None,
        description="Optional market code: sh, hk, or us",
        pattern="^(sh|hk|us)$",
    ),
    limit: int = Query(20, ge=1, le=50),
    fin_indicators_store: StockFinIndicatorsStore = Depends(get_stock_fin_indicators_store),
) -> CoreTickerFinIndicatorsResponse:
    """Financial indicator history for a DojoCore ticker (local jsonl cache with background verify)."""
    try:
        return await fin_indicators_store.get_for_ticker(ticker, market=market, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/ticker/events", response_model=CoreTickerEventsResponse)
async def get_ticker_events(
    ticker: str = Query(..., min_length=1, description="Stock ticker"),
    market: Optional[str] = Query(
        None,
        description="Optional market code: sh, hk, or us",
        pattern="^(sh|hk|us)$",
    ),
    page_size: int = Query(20, ge=1, le=50),
    event_store: StockEventStore = Depends(get_stock_event_store),
) -> CoreTickerEventsResponse:
    """Important corporate events for a DojoCore ticker (local jsonl cache with background refresh)."""
    try:
        return await event_store.get_for_ticker(ticker, market=market, page_size=page_size)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/ticker/news", response_model=CoreTickerNewsResponse)
async def get_ticker_news(
    ticker: str = Query(..., min_length=1, description="Stock ticker"),
    market: Optional[str] = Query(
        None,
        description="Optional market code: sh, hk, or us",
        pattern="^(sh|hk|us)$",
    ),
    page_size: int = Query(20, ge=1, le=50),
    news_store: StockNewsStore = Depends(get_stock_news_store),
) -> CoreTickerNewsResponse:
    """Company news for a DojoCore ticker (local jsonl cache with background refresh)."""
    try:
        return await news_store.get_for_ticker(ticker, market=market, page_size=page_size)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/ticker/kline", response_model=StockKlineResponse)
async def get_ticker_kline(
    ticker: str = Query(..., min_length=1, description="Stock ticker"),
    market: Optional[str] = Query(
        None,
        description="Optional market code: sh, hk, or us",
        pattern="^(sh|hk|us)$",
    ),
    kline_t: str = Query("1D", min_length=1, description="Bar interval, e.g. 5m, 1D, 1W, 1M"),
    limit: int = Query(252, ge=1, le=500),
    stock_store: StockStore = Depends(get_stock_store),
    kline_store: KlineStore = Depends(get_kline_store),
) -> StockKlineResponse:
    """Daily or intraday klines for a DojoCore ticker (disk cache for 1D, live fetch otherwise)."""
    symbol = ticker.strip()
    market_code = (market or stock_store.find_market(symbol) or "").lower()
    if market_code not in ("sh", "hk", "us") or stock_store.get(market_code, symbol) is None:
        raise HTTPException(status_code=404, detail=f"ticker not found: {ticker}")

    response = await kline_store.get_or_fetch_kline(symbol, kline_t=kline_t, limit=limit)
    if response is None:
        raise HTTPException(status_code=404, detail=f"kline not found for {ticker}")
    return response


@router.get("/ticker/income", response_model=CoreTickerIncomeResponse)
async def get_ticker_income(
    ticker: str = Query(..., min_length=1, description="Stock ticker"),
    market: Optional[str] = Query(
        None,
        description="Optional market code: sh, hk, or us",
        pattern="^(sh|hk|us)$",
    ),
    page_size: int = Query(100, ge=1, le=200),
    income_store: StockIncomeStore = Depends(get_stock_income_store),
) -> CoreTickerIncomeResponse:
    """Main business income breakdown by industry, product, and region."""
    try:
        return await income_store.get_for_ticker(ticker, market=market, page_size=page_size)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/ticker/pe-band", response_model=CoreTickerPeBandResponse)
async def get_ticker_pe_band(
    ticker: str = Query(..., min_length=1, description="Stock ticker"),
    market: Optional[str] = Query(
        None,
        description="Optional market code: sh, hk, or us",
        pattern="^(sh|hk|us)$",
    ),
    limit: int = Query(252, ge=1, le=500),
    stock_store: StockStore = Depends(get_stock_store),
    kline_store: KlineStore = Depends(get_kline_store),
    fin_indicators_store: StockFinIndicatorsStore = Depends(get_stock_fin_indicators_store),
) -> CoreTickerPeBandResponse:
    """Trailing-twelve-month P/E band for the past year of daily bars."""
    response = await resolve_core_ticker_pe_band(
        ticker,
        market=market,
        limit=limit,
        stock_store=stock_store,
        kline_store=kline_store,
        fin_indicators_store=fin_indicators_store,
    )
    if response is None:
        raise HTTPException(status_code=404, detail=f"pe band not found for {ticker}")
    return response
