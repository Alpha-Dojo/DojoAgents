from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class StockKlineBar(BaseModel):
    symbol: str = Field(..., description="Ticker symbol")
    kline_t: str = Field("1D", description="Bar interval")
    bar_time: str = Field(..., description="Bar timestamp (ISO or YYYY-MM-DD)")
    open: float = Field(..., description="Open price")
    high: float = Field(..., description="High price")
    low: float = Field(..., description="Low price")
    close: float = Field(..., description="Close price")
    vol: float = Field(0.0, description="Volume")
    amount: float = Field(0.0, description="Turnover amount")
    change_p: float = Field(0.0, description="Change percent")
    tr: float = Field(0.0, description="Turnover rate")
    adj_factor_cum: float = Field(0.0, description="Cumulative adjustment factor")
    dividends: float = Field(0.0, description="Dividends")
    splits: float = Field(0.0, description="Splits")


class StockKlineResponse(BaseModel):
    symbol: str = Field(..., description="Ticker symbol")
    as_of: Optional[str] = Field(None, description="Latest bar date")
    bars: List[StockKlineBar] = Field(default_factory=list, description="Daily bars, oldest first")


class ConstituentKlineBatchResponse(BaseModel):
    as_of: Optional[str] = Field(None, description="Latest bar date across symbols")
    items: Dict[str, StockKlineResponse] = Field(default_factory=dict)


class SectorKlineLevelScope(BaseModel):
    level: str = Field(..., description="Sector level: L1, L2, or L3")
    symbols: List[str] = Field(default_factory=list, description="Constituent tickers at this scope")
    loaded_symbols: int = Field(0, description="Tickers with cached kline data")
    items: Dict[str, StockKlineResponse] = Field(default_factory=dict)


class SectorConstituentKlineResponse(BaseModel):
    level1_id: str = Field(..., description="Level-1 sector id from query_sector_info cache")
    level2_id: str = Field(..., description="Level-2 sector id from query_sector_info cache")
    level3_id: str = Field(..., description="Level-3 sector id from query_sector_info cache")
    market: Optional[str] = Field(
        None,
        description="Optional market filter (sh/hk/us); omitted means all markets",
    )
    as_of: Optional[str] = Field(None, description="Latest bar date across returned items")
    scopes: Dict[str, SectorKlineLevelScope] = Field(
        default_factory=dict,
        description="Cached klines keyed by sector level (L3, L2, L1)",
    )


class ConstituentKlineStatsResponse(BaseModel):
    member_symbols: int = Field(0, description="Eligible L3 constituent tickers across all markets")
    tracked_symbols: int = Field(0, description="Symbols with cache entries")
    loaded_symbols: int = Field(0, description="Symbols with at least one bar")
    initial_load_in_progress: bool = Field(False, description="Background full load running")
    initial_load_complete: bool = Field(False, description="Initial 252-day load finished")
    last_full_refresh_at: Optional[str] = None
    last_incremental_refresh_at: Optional[str] = None
