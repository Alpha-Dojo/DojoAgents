from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class StockQuote(BaseModel):
    ticker: str = Field(..., description="Stock ticker")
    name: str = Field(..., description="Stock name")
    last_price: float = Field(..., description="Stock last price")
    pre_close: float = Field(..., description="Stock pre close price")
    open: float = Field(..., description="Stock open price")
    high: float = Field(..., description="Stock high price")
    low: float = Field(..., description="Stock low price")
    change: float = Field(..., description="Stock price change")
    change_percent: float = Field(..., description="Stock price change percentage")
    volume: int = Field(..., description="Stock volume")
    amount: float = Field(..., description="Stock amount")
    avg_price: float = Field(..., description="Stock average price")
    market_cap: float = Field(..., description="Stock market cap")
    total_shares: float = Field(0.0, description="Total shares outstanding")
    turn_rate: float = Field(..., description="Stock turn rate")
    pe: float = Field(..., description="Stock P/E Ratio")
    pb: float = Field(..., description="Stock P/B Ratio")
    dividend_yield: float = Field(..., description="Stock dividend yield")


class Stock(BaseModel):
    """Core stock profile loaded from local jsonl."""

    ticker: str = Field(..., description="Stock ticker")
    market: str = Field(..., description="Market code: sh, hk, us")
    short_name: Optional[str] = Field(None, description="Short display name")
    long_name: Optional[str] = Field(None, description="Full company name")
    full_exchange_name: Optional[str] = Field(None, description="Exchange name")
    country: Optional[str] = Field(None, description="Country")
    industry: Optional[str] = Field(None, description="Industry")
    sector: Optional[str] = Field(None, description="Sector")
    long_business_summary: Optional[str] = Field(None, description="Business summary")
    currency: Optional[str] = Field(None, description="Trading currency")
    forward_pe: Optional[float] = Field(None, description="Forward P/E from stock basic profile")
    stock_quote: Optional[StockQuote] = Field(None, description="Stock quote")
    is_delisted: Optional[bool] = Field(None, description="Whether delisted")
