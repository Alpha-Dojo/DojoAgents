from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from dojoagents.dashboard.schemas.dojo_mesh import BilingualText

PortfolioAction = Literal["create", "update", "delete"]
AllocationStrategy = Literal["equal_weight", "market_cap", "risk_parity"]
MAX_PORTFOLIO_HOLDINGS_BATCH = 150


class FreshnessEnvelope(BaseModel):
    as_of: Optional[str] = None
    source: Optional[str] = None
    stale: bool = False


class CompanyTickerMatch(BaseModel):
    ticker: str
    market: str = Field(..., description="Market code: us, cn, hk")
    name: BilingualText
    market_cap: float = Field(0.0, description="Latest market cap for ranking")


class CompanyTickerSearchResponse(BaseModel):
    query: str
    items: List[CompanyTickerMatch] = Field(default_factory=list)


class TaxonomyL3Node(BaseModel):
    level3_id: str
    name: BilingualText
    definition: Optional[BilingualText] = None


class TaxonomyL2Node(BaseModel):
    level2_id: str
    name: BilingualText
    description: Optional[BilingualText] = None
    children: List[TaxonomyL3Node] = Field(default_factory=list)


class TaxonomyL1Node(BaseModel):
    level1_id: str
    name: BilingualText
    description: Optional[BilingualText] = None
    children: List[TaxonomyL2Node] = Field(default_factory=list)


class TaxonomyTreeResponse(BaseModel):
    version: str = "api"
    id_scheme: str = "sector_id"
    tree: List[TaxonomyL1Node] = Field(default_factory=list)


class MarketStatsSnapshot(BaseModel):
    market: str
    listed_count: int
    total_market_cap: float
    weighted_pe: Optional[float] = None
    simple_pe: Optional[float] = None
    pe_sample_count: int = 0


class BenchmarkKlinePoint(BaseModel):
    datetime: str
    close: float


class BenchmarkSnapshot(BaseModel):
    market: str
    symbol: str
    name: BilingualText
    price: float
    change_percent: float
    window_start: Optional[str] = None
    window_end: Optional[str] = None
    kline: List[BenchmarkKlinePoint] = Field(default_factory=list)


class MarketOverviewResponse(BaseModel):
    days: int = Field(1, ge=1, le=90)
    window_start: Optional[str] = None
    window_end: Optional[str] = None
    as_of: Optional[str] = None
    markets: Dict[str, MarketStatsSnapshot] = Field(default_factory=dict)
    benchmarks: Dict[str, List[BenchmarkSnapshot]] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_market_payloads(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        markets = data.get("markets")
        if not isinstance(markets, dict):
            return data
        normalized_markets = {}
        benchmarks = dict(data.get("benchmarks") or {})
        window_start = data.get("window_start")
        window_end = data.get("window_end")
        for key, value in markets.items():
            item = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
            if isinstance(item, dict) and "stats" in item:
                normalized_markets[key] = item.get("stats") or {}
                benchmarks.setdefault(key, item.get("benchmarks") or [])
                window_start = window_start or item.get("window_start")
                window_end = window_end or item.get("window_end")
            else:
                normalized_markets[key] = item
        return {**data, "markets": normalized_markets, "benchmarks": benchmarks, "window_start": window_start, "window_end": window_end}


class MarketOverviewMarket(BaseModel):
    market: str
    stats: MarketStatsSnapshot
    default_benchmark: Optional[str] = None
    benchmarks: List[dict[str, Any]] = Field(default_factory=list)
    window_start: Optional[str] = None
    window_end: Optional[str] = None

    @field_validator("stats", mode="before")
    @classmethod
    def coerce_stats(cls, value: object) -> object:
        return value.model_dump(mode="json") if hasattr(value, "model_dump") else value


class SectorMoverMember(BaseModel):
    ticker: str
    name: BilingualText
    last_price: float = 0.0
    market_cap: float = 0.0
    change_percent: float


class SectorMoverItem(BaseModel):
    level1_id: str = ""
    level2_id: str = ""
    level3_id: str = ""
    concept_code: str
    name: BilingualText
    change_percent: float
    avg_market_cap: float = 0.0
    total_market_cap: float = 0.0
    member_count: int = 0
    sample_tickers: List[str] = Field(default_factory=list)
    top_members: List[SectorMoverMember] = Field(default_factory=list)


class MarketSectorMovers(BaseModel):
    gainers: List[SectorMoverItem] = Field(default_factory=list)
    losers: List[SectorMoverItem] = Field(default_factory=list)


class SectorMoversMarket(BaseModel):
    market: str
    days: int
    gainers: List[SectorMoverItem] = Field(default_factory=list)
    losers: List[SectorMoverItem] = Field(default_factory=list)


class SectorMoversResponse(BaseModel):
    days: int = Field(1, ge=0, le=90)
    markets: Dict[str, MarketSectorMovers] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_market_movers(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        markets = data.get("markets")
        if not isinstance(markets, dict):
            return data
        normalized = {}
        for key, value in markets.items():
            item = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
            if isinstance(item, dict):
                normalized[key] = {
                    "gainers": item.get("gainers") or [],
                    "losers": item.get("losers") or [],
                }
            else:
                normalized[key] = item
        return {**data, "markets": normalized}


class StockScreenItem(BaseModel):
    ticker: str
    market: str
    name: BilingualText
    last_price: Optional[float] = None
    change_percent: Optional[float] = None
    window_change_percent: Optional[float] = None
    market_cap: Optional[float] = None
    pe: Optional[float] = None
    pb: Optional[float] = None


class StockScreenResponse(BaseModel):
    days: int = Field(0, ge=0, le=90)
    market: Optional[str] = None
    window_start: Optional[str] = None
    as_of: Optional[str] = None
    universe_count: int = 0
    match_count: int = 0
    items: List[StockScreenItem] = Field(default_factory=list)


class SectorMarketMetrics(BaseModel):
    market: str
    member_count: int = 0
    total_market_cap: float = 0.0
    weighted_pe: Optional[float] = None
    pe_sample_count: int = 0


class SectorPerformancePoint(BaseModel):
    date: str
    value: float


class SectorPerformanceStats(BaseModel):
    cumulative_return_pct: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    calmar_ratio: Optional[float] = None
    volatility_pct: Optional[float] = None
    trading_days: int = 0


class SectorScopePerformance(BaseModel):
    performance_window_start: Optional[str] = None
    performance_window_end: Optional[str] = None
    performance_by_market: Dict[str, List[SectorPerformancePoint]] = Field(default_factory=dict)
    stats_by_market: Dict[str, SectorPerformanceStats] = Field(default_factory=dict)
    members_by_market: Dict[str, int] = Field(default_factory=dict)


class SectorAnalysisScope(BaseModel):
    scope: str
    metrics: Dict[str, Any] = Field(default_factory=dict)
    performance: Dict[str, Any] = Field(default_factory=dict)


class SectorAnalysisResponse(BaseModel):
    level1_id: str
    level2_id: str
    level3_id: str
    scope: str = "L3"
    metrics_by_scope: Dict[str, Dict[str, SectorMarketMetrics]] = Field(default_factory=dict)
    performance_window_start: Optional[str] = None
    performance_window_end: Optional[str] = None
    performance_by_market: Dict[str, List[SectorPerformancePoint]] = Field(default_factory=dict)
    stats_by_market: Dict[str, SectorPerformanceStats] = Field(default_factory=dict)
    members_by_market: Dict[str, int] = Field(default_factory=dict)
    performance_by_scope: Dict[str, SectorScopePerformance] = Field(default_factory=dict)
    # Compatibility field for existing dashboard-side tests and callers.
    scopes: Dict[str, SectorAnalysisScope] = Field(default_factory=dict, exclude=True)


class SectorConstituentRow(BaseModel):
    ticker: str
    market: str
    name: BilingualText
    currency: str = ""
    last_price: Optional[float] = None
    change_percent: Optional[float] = None
    window_change_percent: Optional[float] = None
    turn_rate: Optional[float] = None
    market_cap: Optional[float] = None
    pe: Optional[float] = None
    pb: Optional[float] = None
    amount: Optional[float] = None


class SectorConstituentsResponse(BaseModel):
    level1_id: str
    level2_id: str
    level3_id: str
    scope: str = "L3"
    market: Optional[str] = None
    count: int = 0
    items: List[SectorConstituentRow] = Field(default_factory=list)


SectorConstituentsResponseV1 = SectorConstituentsResponse


class TickerSectorPath(BaseModel):
    role: Literal["primary", "secondary"] = "primary"
    level1_id: str
    level2_id: str
    level3_id: str
    labels: Dict[str, BilingualText] = Field(default_factory=dict)


class TickerQuoteResponseV1(BaseModel):
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
    dividend_yield: Optional[float] = None
    exchange_name: Optional[str] = None
    industry: Optional[str] = None
    sector: Optional[str] = None
    country: Optional[str] = None
    sector_paths: List[TickerSectorPath] = Field(default_factory=list)


MAX_TICKER_QUOTES_BATCH = 50
MAX_TICKER_FINANCIALS_BATCH = 50


class TickerQuotesBatchResponseV1(BaseModel):
    market: Optional[str] = None
    count: int = 0
    not_found: List[str] = Field(default_factory=list)
    items: List[TickerQuoteResponseV1] = Field(default_factory=list)


class IncomeDistributionSlice(BaseModel):
    dimension: Literal["industry", "product", "region"]
    report_date: Optional[str] = None
    items: List[Dict[str, float | str]] = Field(default_factory=list)


class TickerFinancialsResponseV1(BaseModel):
    ticker: str
    market: str
    report_type: Optional[str] = None
    as_of: Optional[str] = None
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    pe: Optional[float] = Field(None, description="Trailing/dynamic P/E from live quote when absent in indicators")
    pb: Optional[float] = Field(None, description="P/B from live quote when absent in indicators")
    indicators: List[Dict[str, Any]] = Field(default_factory=list)
    income_distributions: List[IncomeDistributionSlice] = Field(default_factory=list)


class TickerFinancialsBatchResponseV1(BaseModel):
    market: Optional[str] = None
    count: int = 0
    not_found: List[str] = Field(default_factory=list)
    items: List[TickerFinancialsResponseV1] = Field(default_factory=list)


class TickerNewsItem(BaseModel):
    title: str = ""
    summary: str = ""
    published_at: Optional[str] = None
    source: Optional[str] = None
    url: Optional[str] = None


class TickerEventItem(BaseModel):
    event_type: str = ""
    title: str = ""
    event_date: Optional[str] = None
    description: str = ""


class TickerNewsEventsResponseV1(BaseModel):
    ticker: str
    market: str
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    news: List[TickerNewsItem] = Field(default_factory=list)
    events: List[TickerEventItem] = Field(default_factory=list)


class KlineBar(BaseModel):
    datetime: str
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = None


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
    interval: str = "1D"
    as_of: Optional[str] = None
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    klines: List[KlineBar] = Field(default_factory=list)
    pe_band: List[PeBandPoint] = Field(default_factory=list)

    @property
    def kline_t(self) -> str:
        return self.interval

    @property
    def bars(self) -> List[KlineBar]:
        return self.klines

    @property
    def pe_points(self) -> List[PeBandPoint]:
        return self.pe_band


class PortfolioSummaryItem(BaseModel):
    id: str
    name: str
    subtitle: Optional[str] = None
    kind: Literal["manual", "agent"] = "manual"
    pinned: bool = False
    today_change: Optional[float] = None
    net_value_usd: Optional[float] = None


class PortfolioListResponseV1(BaseModel):
    query: Optional[str] = None
    items: List[PortfolioSummaryItem] = Field(default_factory=list)


class PortfolioCandidateRow(BaseModel):
    ticker: str
    name: str
    name_zh: str = ""
    name_en: str = ""
    market: str
    price: float = 0.0
    change_percent: float = 0.0
    market_cap: float = 0.0
    pe: Optional[float] = None
    pb: Optional[float] = None
    dividend_yield: Optional[float] = None
    eps: Optional[float] = None
    turn_rate: Optional[float] = None
    sector_l1: str = ""
    sector_l2: str = ""
    sector_l3: str = ""


class PortfolioHoldingRow(BaseModel):
    ticker: str
    name: str
    name_zh: str = ""
    name_en: str = ""
    market: str
    shares: float
    weight: float = 0.0
    cost: float = 0.0
    cost_low: Optional[float] = None
    cost_high: Optional[float] = None
    uses_default_cost: bool = True
    cost_date: Optional[str] = None
    open_date: Optional[str] = None
    uses_default_open_date: bool = True
    cost_basis: float = 0.0
    price: float = 0.0
    change_percent: float = 0.0
    total_return_pct: Optional[float] = None
    market_value: float = 0.0
    sector_l1: str = ""
    sector_l2: str = ""
    sector_l3: str = ""


class PortfolioKpi(BaseModel):
    key: Literal["netValue", "cumulativeReturn", "sharpe", "maxDrawdown"]
    value: str
    delta: Optional[str] = None
    delta_tone: Optional[Literal["positive", "negative", "neutral", "risk"]] = None


class PortfolioOrderRow(BaseModel):
    id: str
    ticker: str
    name: str = ""
    name_zh: str = ""
    name_en: str = ""
    market: str
    order_side: Literal["buy", "sell"]
    order_status: Literal["pending", "filled", "cancelled", "rejected"] = "pending"
    price: float = 0.0
    qty: float = 0.0
    order_time: Optional[str] = None
    fill_time: Optional[str] = None
    fill_price: Optional[float] = None
    created_at: str = ""


class PortfolioAnalysisResponseV1(BaseModel):
    id: str = ""
    name: str = ""
    subtitle: Optional[str] = None
    kind: Literal["manual", "agent"] = "manual"
    pinned: bool = False
    today_change: Optional[float] = None
    net_value_usd: Optional[float] = None
    benchmark: Optional[str] = None
    start_date: Optional[str] = None
    capital_by_market: Dict[str, float] = Field(default_factory=dict)
    candidates: List[PortfolioCandidateRow] = Field(default_factory=list)
    holdings: List[PortfolioHoldingRow] = Field(default_factory=list)
    kpis: List[PortfolioKpi] = Field(default_factory=list)
    performance_window_start: Optional[str] = None
    performance_window_end: Optional[str] = None
    nav_by_market: Dict[str, List[SectorPerformancePoint]] = Field(default_factory=dict)
    candidate_nav_by_market: Dict[str, List[SectorPerformancePoint]] = Field(default_factory=dict)
    benchmark_by_market: Dict[str, List[SectorPerformancePoint]] = Field(default_factory=dict)
    benchmark_symbol_by_market: Dict[str, str] = Field(default_factory=dict)
    stats_by_market: Dict[str, SectorPerformanceStats] = Field(default_factory=dict)
    candidate_stats_by_market: Dict[str, SectorPerformanceStats] = Field(default_factory=dict)
    net_value_by_market: Dict[str, float] = Field(default_factory=dict)
    cost_basis_by_market: Dict[str, float] = Field(default_factory=dict)
    orders: List[PortfolioOrderRow] = Field(default_factory=list)


class PortfolioPerformanceResponseV1(BaseModel):
    id: str = ""
    benchmark: Optional[str] = None
    start_date: Optional[str] = None
    performance_window_start: Optional[str] = None
    performance_window_end: Optional[str] = None
    nav_by_market: Dict[str, List[SectorPerformancePoint]] = Field(default_factory=dict)
    candidate_nav_by_market: Dict[str, List[SectorPerformancePoint]] = Field(default_factory=dict)
    benchmark_by_market: Dict[str, List[SectorPerformancePoint]] = Field(default_factory=dict)
    benchmark_symbol_by_market: Dict[str, str] = Field(default_factory=dict)
    stats_by_market: Dict[str, SectorPerformanceStats] = Field(default_factory=dict)
    candidate_stats_by_market: Dict[str, SectorPerformanceStats] = Field(default_factory=dict)


class ManagePortfolioRequestV1(BaseModel):
    action: PortfolioAction
    portfolio_id: Optional[str] = Field(None, description="Required for update/delete")
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    description: Optional[str] = Field(None, max_length=240)
    kind: Optional[Literal["manual", "agent"]] = None
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


class AddHoldingDetails(BaseModel):
    ticker: str = Field(..., min_length=1)
    market: Optional[str] = Field(None, description="Market code: us, cn, hk")
    shares: Optional[float] = Field(None, ge=0)


class AddPortfolioHoldingRequestV1(BaseModel):
    portfolio_id: str
    holding_details: AddHoldingDetails

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_flat_body(cls, data: object) -> object:
        if not isinstance(data, dict) or "holding_details" in data:
            return data
        if "ticker" not in data:
            return data
        return {
            "portfolio_id": data.get("portfolio_id"),
            "holding_details": {
                "ticker": data.get("ticker"),
                "market": data.get("market"),
                "shares": data.get("shares"),
            },
        }


class AddPortfolioHoldingsRequestV1(BaseModel):
    portfolio_id: str
    holdings: List[AddHoldingDetails] = Field(..., min_length=1, max_length=MAX_PORTFOLIO_HOLDINGS_BATCH)


class RemovePortfolioHoldingRequestV1(BaseModel):
    portfolio_id: str
    ticker: str = Field(..., min_length=1)
    market: Optional[str] = Field(None, description="Market code: us, cn, hk")


class AutoAllocateRequestV1(BaseModel):
    portfolio_id: str
    allocation_strategy: AllocationStrategy = "market_cap"
    market: Optional[str] = Field(None, description="Optional market scope: us, cn, hk")


class UpdateHoldingsMetadataRequestV1(BaseModel):
    portfolio_id: str
    open_date_by_ticker: Optional[Dict[str, Optional[str]]] = None
    shares_by_ticker: Optional[Dict[str, float]] = None


class CreatePortfolioOrderRequestV1(BaseModel):
    portfolio_id: str
    ticker: str = Field(..., min_length=1)
    market: Optional[str] = Field(None, description="Market code: us, cn, hk")
    order_side: Literal["buy", "sell"]
    price: float = Field(..., gt=0)
    qty: float = Field(..., gt=0)
    order_time: Optional[str] = Field(None, description="Optional execution date (YYYY-MM-DD or ISO)")


class CancelPortfolioOrderRequestV1(BaseModel):
    portfolio_id: str
    order_id: str = Field(..., min_length=1)


AddPortfolioHoldingRequest = AddPortfolioHoldingRequestV1
RemovePortfolioHoldingRequest = RemovePortfolioHoldingRequestV1
AutoAllocateRequest = AutoAllocateRequestV1
