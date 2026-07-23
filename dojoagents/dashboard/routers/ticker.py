from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from dojoagents.dashboard.deps import get_financial_registry
from dojoagents.dashboard.schemas.domain_api import (
    TickerFinancialsResponseV1,
    TickerNewsEventsResponseV1,
    TickerPriceTrendsResponseV1,
    TickerQuoteResponseV1,
)
from dojoagents.dashboard.services.domain_api import (
    build_ticker_financials_v1,
    build_ticker_news_events_v1,
    build_ticker_price_trends_v1,
    build_ticker_quote_v1,
)
from dojoagents.dashboard.services.domain_utils import validate_date_range

router = APIRouter(prefix="/ticker", tags=["ticker-scan"])


@router.get(
    "/quote",
    response_model=TickerQuoteResponseV1,
    operation_id="get_ticker_realtime_quote",
    summary="Latest quote, valuation, and L1-L2-L3 sector paths",
)
async def ticker_quote(
    ticker: str = Query(..., min_length=1),
    market: Optional[str] = Query(None, pattern="^(cn|sh|hk|us)$"),
    registry=Depends(get_financial_registry),
) -> TickerQuoteResponseV1:
    response = await build_ticker_quote_v1(registry, ticker=ticker, market=market)
    if response is None:
        raise HTTPException(status_code=404, detail=f"quote not found for {ticker}")
    return response


@router.get(
    "/financials",
    response_model=TickerFinancialsResponseV1,
    operation_id="get_ticker_financials",
    summary="Financial indicators and revenue breakdown by business/region",
)
async def ticker_financials(
    ticker: str = Query(..., min_length=1),
    market: Optional[str] = Query(None, pattern="^(cn|sh|hk|us)$"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: Optional[int] = Query(20, ge=1, le=200),
    report_type: Optional[str] = Query(None, pattern="^(accumulate|quarter)$"),
    registry=Depends(get_financial_registry),
) -> TickerFinancialsResponseV1:
    try:
        validate_date_range(start_date, end_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    response = await build_ticker_financials_v1(
        registry,
        ticker=ticker,
        market=market,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        report_type=report_type,
    )
    if response is None:
        raise HTTPException(status_code=404, detail=f"financials not found for {ticker}")
    return response


@router.get(
    "/news-events",
    response_model=TickerNewsEventsResponseV1,
    operation_id="get_ticker_news_and_events",
    summary="Recent news, ratings, and corporate events",
)
async def ticker_news_events(
    ticker: str = Query(..., min_length=1),
    market: Optional[str] = Query(None, pattern="^(cn|sh|hk|us)$"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    page_size: Optional[int] = Query(20, ge=1, le=200),
    registry=Depends(get_financial_registry),
) -> TickerNewsEventsResponseV1:
    try:
        validate_date_range(start_date, end_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    response = await build_ticker_news_events_v1(
        registry,
        ticker=ticker,
        market=market,
        start_date=start_date,
        end_date=end_date,
        page_size=page_size,
    )
    if response is None:
        raise HTTPException(status_code=404, detail=f"news/events not found for {ticker}")
    return response


@router.get(
    "/price-trends",
    response_model=TickerPriceTrendsResponseV1,
    operation_id="get_ticker_price_trends",
    summary="Historical OHLCV bars and trailing P/E band",
)
async def ticker_price_trends(
    ticker: str = Query(..., min_length=1),
    market: Optional[str] = Query(None, pattern="^(cn|sh|hk|us)$"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: Optional[int] = Query(None, ge=0, le=500),
    kline_t: str = Query("1D", min_length=1),
    registry=Depends(get_financial_registry),
) -> TickerPriceTrendsResponseV1:
    try:
        validate_date_range(start_date, end_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    response = await build_ticker_price_trends_v1(
        registry,
        ticker=ticker,
        market=market,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        kline_t=kline_t,
    )
    if response is None:
        raise HTTPException(status_code=404, detail=f"price trends not found for {ticker}")
    return response
