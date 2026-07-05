from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

PortfolioKind = Literal["manual", "agent"]
PortfolioMatchType = Literal["name", "holding", "candidate"]
OrderSide = Literal["buy", "sell"]
OrderStatus = Literal["pending", "filled", "cancelled", "rejected"]


class PortfolioCapitalConfig(BaseModel):
    start_date: str = Field(..., description="Portfolio backtest start date (YYYY-MM-DD)")
    cost_date: Optional[str] = Field(
        None,
        description="Cost basis date (YYYY-MM-DD); defaults to start_date when omitted",
    )
    capital_by_market: Dict[str, float] = Field(
        default_factory=lambda: {"us": 1_000_000.0, "sh": 1_000_000.0, "hk": 1_000_000.0},
        description="Initial capital per market in local currency",
    )


class PortfolioCandidateRecord(BaseModel):
    ticker: str
    market: str
    added_at: str = Field(..., description="ISO timestamp when the candidate was added")


class PortfolioOrderRecord(BaseModel):
    id: str
    ticker: str
    market: str
    order_side: OrderSide
    order_status: OrderStatus = "pending"
    price: float = Field(..., gt=0)
    qty: float = Field(..., gt=0)
    order_time: Optional[str] = Field(None, description="Optional execution date (YYYY-MM-DD or ISO)")
    fill_time: Optional[str] = None
    fill_price: Optional[float] = None
    created_at: str
    updated_at: Optional[str] = None


class PortfolioCandidateView(BaseModel):
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
    sector: str = ""
    sector_l1: str = ""
    sector_l2: str = ""
    sector_l3: str = ""


class PortfolioOrderView(PortfolioOrderRecord):
    name: str = ""
    name_zh: str = ""
    name_en: str = ""


class PortfolioHoldingRecord(BaseModel):
    ticker: str
    market: str
    shares: float = 0.0
    added_at: str = Field(..., description="ISO timestamp when the holding was added")


class PortfolioSummary(BaseModel):
    id: str
    name: str
    subtitle: Optional[str] = None
    kind: PortfolioKind = "manual"
    pinned: bool = False
    today_change: Optional[float] = None
    net_value_usd: Optional[float] = None


class PortfolioHoldingView(BaseModel):
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
    cost_basis: float = 0.0
    open_date: Optional[str] = None
    uses_default_open_date: bool = True
    manual_shares: bool = False
    shares_locked: bool = False
    open_date_locked: bool = False
    cost_locked: bool = False
    price: float = 0.0
    change_percent: float = 0.0
    sector: str = ""
    sector_l1: str = ""
    sector_l2: str = ""
    sector_l3: str = ""
    market_value: float = 0.0


class PortfolioPositionView(PortfolioHoldingView):
    """Filled position derived from order history."""


class PortfolioKpiView(BaseModel):
    key: Literal["netValue", "cumulativeReturn", "sharpe", "maxDrawdown"]
    value: str
    delta: Optional[str] = None
    delta_tone: Optional[Literal["positive", "negative", "neutral", "risk"]] = None
    hint: Optional[str] = None


class PortfolioPerformanceView(BaseModel):
    dates: List[str] = Field(default_factory=list)
    portfolio: List[float] = Field(default_factory=list)
    benchmark: List[float] = Field(default_factory=list)
    window_start: Optional[str] = None
    window_end: Optional[str] = None
    series_by_market: Dict[str, "PortfolioMarketPerformance"] = Field(default_factory=dict)
    candidate_series_by_market: Dict[str, List[dict]] = Field(default_factory=dict)
    benchmark_by_market: Dict[str, List[float]] = Field(default_factory=dict)
    benchmark_symbol_by_market: Dict[str, str] = Field(default_factory=dict)
    stats_by_market: Dict[str, "PortfolioRiskStats"] = Field(default_factory=dict)
    candidate_stats_by_market: Dict[str, "PortfolioRiskStats"] = Field(default_factory=dict)


class PortfolioRiskStats(BaseModel):
    cumulative_return_pct: Optional[float] = None
    volatility_pct: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    calmar_ratio: Optional[float] = None
    trading_days: int = 0


class PortfolioMarketPerformance(BaseModel):
    market: str
    dates: List[str] = Field(default_factory=list)
    portfolio: List[float] = Field(default_factory=list)
    benchmark: List[float] = Field(default_factory=list)
    benchmark_symbol: str
    stats: PortfolioRiskStats = Field(default_factory=PortfolioRiskStats)


class PortfolioDetail(PortfolioSummary):
    config: Optional[PortfolioCapitalConfig] = None
    candidates: List[PortfolioCandidateView] = Field(default_factory=list)
    positions: List[PortfolioPositionView] = Field(default_factory=list)
    orders: List[PortfolioOrderView] = Field(default_factory=list)
    holdings: List[PortfolioHoldingView] = Field(default_factory=list)
    kpis: Optional[List[PortfolioKpiView]] = None
    performance: Optional[PortfolioPerformanceView] = None
    net_value_by_market: Dict[str, float] = Field(
        default_factory=lambda: {"us": 0.0, "sh": 0.0, "hk": 0.0},
    )
    cost_basis_by_market: Dict[str, float] = Field(
        default_factory=lambda: {"us": 0.0, "sh": 0.0, "hk": 0.0},
    )


class CreatePortfolioRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    kind: PortfolioKind = "manual"


class UpdatePortfolioRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    kind: Optional[PortfolioKind] = None
    pinned: Optional[bool] = None
    config: Optional[PortfolioCapitalConfig] = None
    shares_by_ticker: Optional[Dict[str, float]] = None
    manual_shares_by_ticker: Optional[Dict[str, bool]] = None
    open_date_by_ticker: Optional[Dict[str, Optional[str]]] = None
    shares_locked_by_ticker: Optional[Dict[str, bool]] = None
    open_date_locked_by_ticker: Optional[Dict[str, bool]] = None
    cost_locked_by_ticker: Optional[Dict[str, bool]] = None
    cost_override_by_ticker: Optional[Dict[str, Optional[float]]] = None


class AutoAllocateRequest(BaseModel):
    market: Optional[str] = Field(None, description="Optional market code: us, sh, hk")


class AddPortfolioHoldingRequest(BaseModel):
    """Adds a candidate ticker to the portfolio watchlist."""

    ticker: str = Field(..., min_length=1)
    market: Optional[str] = Field(None, description="Market code: us, sh, hk")
    shares: Optional[float] = Field(None, ge=0, description="Deprecated; ignored for candidates")


class AddPortfolioCandidateRequest(AddPortfolioHoldingRequest):
    pass


class ResolvedOrderBar(BaseModel):
    date: str = Field(..., description="Trading day YYYY-MM-DD")
    open: float = Field(..., gt=0)
    low: float = Field(..., gt=0)
    high: float = Field(..., gt=0)


class CreatePortfolioOrderRequest(BaseModel):
    ticker: str = Field(..., min_length=1)
    market: Optional[str] = Field(None, description="Market code: us, sh, hk")
    order_side: OrderSide
    price: float = Field(..., gt=0)
    qty: float = Field(..., gt=0)
    order_time: Optional[str] = Field(None, description="Optional execution date (YYYY-MM-DD or ISO)")
    resolved_bar: Optional[ResolvedOrderBar] = Field(
        None,
        description="Kline bar validated during order resolution; reused at fill time to avoid refetch",
    )


class CancelPortfolioOrderRequest(BaseModel):
    order_id: str = Field(..., min_length=1)


class RemovePortfolioHoldingRequest(BaseModel):
    """Removes a candidate ticker from the portfolio watchlist."""
    ticker: str = Field(..., min_length=1)
    market: Optional[str] = Field(None, description="Market code: us, sh, hk")


class RemovePortfolioHoldingsBatchRequest(BaseModel):
    """Removes multiple candidate tickers from the portfolio watchlist."""

    holdings: list[RemovePortfolioHoldingRequest] = Field(..., min_length=1)


class PortfolioSearchItem(BaseModel):
    id: str
    match_type: PortfolioMatchType
    matched_ticker: Optional[str] = None
    matched_name: Optional[str] = None


class PortfolioSearchResponse(BaseModel):
    query: str
    items: List[PortfolioSearchItem] = Field(default_factory=list)
