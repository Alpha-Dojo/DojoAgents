from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from dojoagents.dashboard.schemas.dojo_core import (
    CoreSectorOption,
    CoreTickerSearchItem,
)
from dojoagents.dashboard.schemas.dojo_mesh import BilingualText, SectorItem
from dojoagents.dashboard.schemas.dojo_sphere import (
    SectorConstituentItem,
)
from dojoagents.dashboard.schemas.market import MarketStats
from dojoagents.dashboard.schemas.portfolio import (
    AddPortfolioHoldingRequest,
    AutoAllocateRequest,
    PortfolioDetail,
    PortfolioSummary,
    RemovePortfolioHoldingRequest,
)
from dojoagents.dashboard.schemas.stock_kline import StockKlineBar


class FreshnessEnvelope(BaseModel):
    as_of: Optional[str] = None
    source: Optional[str] = None
    stale: bool = False


class CompanyTickerSearchResponse(BaseModel):
    query: str
    items: List[CoreTickerSearchItem] = Field(default_factory=list)


class TaxonomyTreeResponse(BaseModel):
    taxonomy: Dict[str, Any] = Field(default_factory=dict)


class MarketOverviewMarket(BaseModel):
    market: str
    stats: MarketStats
    default_benchmark: Optional[str] = None
    benchmarks: List[dict[str, Any]] = Field(default_factory=list)
    window_start: Optional[str] = None
    window_end: Optional[str] = None


class MarketOverviewResponse(FreshnessEnvelope):
    days: int = 1
    markets: Dict[str, MarketOverviewMarket] = Field(default_factory=dict)


class SectorMoversMarket(BaseModel):
    market: str
    days: int
    gainers: List[SectorItem] = Field(default_factory=list)
    losers: List[SectorItem] = Field(default_factory=list)


class SectorMoversResponse(FreshnessEnvelope):
    days: int
    markets: Dict[str, SectorMoversMarket] = Field(default_factory=dict)


class SectorAnalysisScope(BaseModel):
    scope: str
    metrics: Dict[str, Any] = Field(default_factory=dict)
    performance: Dict[str, Any] = Field(default_factory=dict)


class SectorAnalysisResponse(FreshnessEnvelope):
    level1_id: str
    level2_id: str
    level3_id: str
    scope: str = "L3"
    scopes: Dict[str, SectorAnalysisScope] = Field(default_factory=dict)


class SectorConstituentsResponseV1(FreshnessEnvelope):
    level1_id: str
    level2_id: str
    level3_id: str
    scope: str = "L3"
    market: Optional[str] = None
    days: int = 1
    items: List[SectorConstituentItem] = Field(default_factory=list)


class TickerQuoteResponseV1(FreshnessEnvelope):
    ticker: str
    market: str
    name: BilingualText = Field(default_factory=BilingualText)
    currency: Optional[str] = None
    last_price: float = 0.0
    change: float = 0.0
    change_percent: float = 0.0
    pre_close: float = 0.0
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    volume: int = 0
    amount: Optional[float] = None
    total_shares: Optional[float] = None
    market_cap: float = 0.0
    pe: float = 0.0
    forward_pe: Optional[float] = None
    pb: float = 0.0
    turn_rate: float = 0.0
    exchange_name: Optional[str] = None
    industry: Optional[str] = None
    sector: Optional[str] = None
    country: Optional[str] = None
    sector_options: List[CoreSectorOption] = Field(default_factory=list)


class TickerFinancialsResponseV1(FreshnessEnvelope):
    ticker: str
    market: str
    report_type: str
    items: List[dict[str, Any]] = Field(default_factory=list)
    distributions: List[dict[str, Any]] = Field(default_factory=list)
    report_date: Optional[str] = None


class TickerNewsEventsResponseV1(BaseModel):
    ticker: str
    market: str
    news: FreshnessEnvelope = Field(default_factory=FreshnessEnvelope)
    events: FreshnessEnvelope = Field(default_factory=FreshnessEnvelope)
    news_items: List[dict[str, Any]] = Field(default_factory=list)
    event_items: List[dict[str, Any]] = Field(default_factory=list)


class PeBandPoint(BaseModel):
    date: str
    pe: float
    mean: float
    upper1: float
    lower1: float
    upper2: float
    lower2: float


class TickerPriceTrendsResponseV1(BaseModel):
    ticker: str
    market: str
    kline_t: str = "1D"
    kline: FreshnessEnvelope = Field(default_factory=FreshnessEnvelope)
    pe_band: FreshnessEnvelope = Field(default_factory=FreshnessEnvelope)
    bars: List[StockKlineBar] = Field(default_factory=list)
    pe_points: List[PeBandPoint] = Field(default_factory=list)


class PortfolioListResponseV1(FreshnessEnvelope):
    items: List[PortfolioSummary] = Field(default_factory=list)


class PortfolioAnalysisResponseV1(FreshnessEnvelope):
    detail: Optional[PortfolioDetail] = None


class ManagePortfolioRequestV1(BaseModel):
    action: Literal["create", "update", "delete"]
    portfolio_id: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    pinned: Optional[bool] = None
    start_date: Optional[str] = None
    capital_by_market: Optional[Dict[str, float]] = None
    config: Optional[dict[str, Any]] = None
    shares_by_ticker: Optional[Dict[str, float]] = None
    manual_shares_by_ticker: Optional[Dict[str, bool]] = None
    open_date_by_ticker: Optional[Dict[str, Optional[str]]] = None
    shares_locked_by_ticker: Optional[Dict[str, bool]] = None
    open_date_locked_by_ticker: Optional[Dict[str, bool]] = None
    cost_locked_by_ticker: Optional[Dict[str, bool]] = None
    cost_override_by_ticker: Optional[Dict[str, Optional[float]]] = None


class AddPortfolioHoldingRequestV1(AddPortfolioHoldingRequest):
    portfolio_id: str


class RemovePortfolioHoldingRequestV1(RemovePortfolioHoldingRequest):
    portfolio_id: str


class AutoAllocateRequestV1(AutoAllocateRequest):
    portfolio_id: str
