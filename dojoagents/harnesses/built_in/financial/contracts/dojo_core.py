from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from dojoagents.harnesses.built_in.financial.contracts.dojo_mesh import BilingualText


class CoreTickerSearchItem(BaseModel):
    ticker: str
    market: str = Field(..., description="Market code: sh, hk, or us")
    name: BilingualText
    market_cap: float = Field(0.0, description="Latest quote market cap for ranking")


class CoreTickerSearchResponse(BaseModel):
    query: str
    items: List[CoreTickerSearchItem] = Field(default_factory=list)


class CoreSectorCrumb(BaseModel):
    level: Literal["L1", "L2", "L3"] = Field(..., description="Industry level for this crumb")
    name: BilingualText = Field(..., description="Display name")
    level1_id: str = Field(..., description="Level-1 sector id for DojoSphere navigation")
    level2_id: str = Field(..., description="Level-2 sector id for DojoSphere navigation")
    level3_id: str = Field(..., description="Level-3 sector id for DojoSphere navigation")


class CoreSectorLabelPath(BaseModel):
    level_1: BilingualText = Field(..., description="Level-1 label from stock sector assignment")
    level_2: BilingualText = Field(..., description="Level-2 label from stock sector assignment")
    level_3: BilingualText = Field(..., description="Level-3 label from stock sector assignment")


class CoreSectorOption(BaseModel):
    role: Literal["primary", "secondary"] = Field(..., description="Classification role")
    level1_id: str
    level2_id: str
    level3_id: str
    label: CoreSectorLabelPath = Field(..., description="Assigned L1/L2/L3 labels")


class CoreTickerSectorResponse(BaseModel):
    ticker: str
    market: str = Field(..., description="Market code: sh, hk, or us")
    sector_options: List[CoreSectorOption] = Field(
        default_factory=list,
        description="Resolvable primary and secondary sector paths for the ticker",
    )


class CoreTickerQuoteResponse(BaseModel):
    ticker: str
    market: str = Field(..., description="Market code: sh, hk, or us")
    currency: Optional[str] = Field(None, description="Trading currency from stock profile")
    last_price: float = Field(..., description="Latest traded price")
    change: float = Field(..., description="Price change vs previous close")
    change_percent: float = Field(..., description="Price change percentage vs previous close")
    pre_close: float = Field(..., description="Previous close price")
    open: float = Field(..., description="Session open price")
    high: float = Field(..., description="Session high price")
    low: float = Field(..., description="Session low price")
    volume: int = Field(..., description="Session volume")
    amount: Optional[float] = Field(None, description="Session turnover amount")
    total_shares: Optional[float] = Field(None, description="Total shares outstanding")
    market_cap: float = Field(..., description="Market capitalization")
    pe: float = Field(..., description="Price-to-earnings ratio")
    forward_pe: Optional[float] = Field(None, description="Forward P/E from stock basic profile")
    pb: float = Field(..., description="Price-to-book ratio")
    dividend_yield: Optional[float] = Field(None, description="dividend yield")
    turn_rate: float = Field(..., description="Turnover rate")
    exchange_name: Optional[str] = Field(None, description="Listing exchange name")
    industry: Optional[str] = Field(None, description="Industry classification")
    sector: Optional[str] = Field(None, description="Sector classification")
    country: Optional[str] = Field(None, description="Country of incorporation")


class CorePeBandPoint(BaseModel):
    date: str = Field(..., description="Trading date (YYYY-MM-DD)")
    pe: float = Field(..., description="Trailing-twelve-month P/E")
    mean: float = Field(..., description="Mean P/E over the returned window")
    upper1: float = Field(..., description="Mean + 1 standard deviation")
    lower1: float = Field(..., description="Mean - 1 standard deviation")
    upper2: float = Field(..., description="Mean + 2 standard deviations")
    lower2: float = Field(..., description="Mean - 2 standard deviations")


class CoreTickerPeBandResponse(BaseModel):
    ticker: str
    market: str = Field(..., description="Market code: sh, hk, or us")
    as_of: Optional[str] = Field(None, description="Latest kline bar date")
    total_shares: float = Field(..., description="Shares used for daily market cap")
    points: List[CorePeBandPoint] = Field(default_factory=list)
