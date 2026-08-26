from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from dojoagents.dashboard.schemas.dojo_mesh import BilingualText

SectorLevelKey = str
MarketKey = str


class SectorScopeMarketStats(BaseModel):
    market: str = Field(..., description="Market code: sh, hk, us")
    member_count: int = Field(0, description="Eligible constituents in this scope")
    total_market_cap: float = Field(0.0, description="Sum of stock_quote.market_cap")
    weighted_pe: Optional[float] = Field(
        None,
        description="Market-cap weighted PE for scope constituents",
    )
    pe_sample_count: int = Field(0, description="Constituents with valid positive PE")


class SectorScopeMetricsResponse(BaseModel):
    level1_id: str
    level2_id: str
    level3_id: str
    as_of: Optional[str] = None
    source: str = "computed"
    stale: bool = False
    scopes: Dict[SectorLevelKey, Dict[MarketKey, SectorScopeMarketStats]] = Field(
        default_factory=dict,
        description="L1/L2/L3 → market → aggregate stats",
    )


class SectorConstituentItem(BaseModel):
    ticker: str
    market: str = Field(..., description="Market code: sh, hk, us")
    name: BilingualText
    currency: str
    last_price: Optional[float] = None
    change_percent: Optional[float] = None
    window_change_percent: Optional[float] = Field(
        None,
        description="Total return since the sector performance curve window start (%)",
    )
    turn_rate: Optional[float] = Field(None, description="Daily turnover rate from quote")
    market_cap: Optional[float] = None
    pe: Optional[float] = None
    pb: Optional[float] = None
    amount: Optional[float] = Field(None, description="Daily trading amount from quote")


class SectorConstituentsResponse(BaseModel):
    level1_id: str
    level2_id: str
    level3_id: str
    scope: str = Field("L3", description="Constituent scope level: L1, L2, or L3")
    market: Optional[str] = Field(None, description="Optional filter: sh, hk, or us")
    items: List[SectorConstituentItem] = Field(default_factory=list)


class SectorPerformancePoint(BaseModel):
    date: str = Field(..., description="Trading day (YYYY-MM-DD)")
    us: Optional[float] = Field(None, description="US market cap-weighted index (base 100)")
    sh: Optional[float] = Field(None, description="CN (sh) market cap-weighted index (base 100)")
    hk: Optional[float] = Field(None, description="HK market cap-weighted index (base 100)")


class SectorPerformanceMarketPoint(BaseModel):
    date: str = Field(..., description="Trading day on this market's calendar (YYYY-MM-DD)")
    value: float = Field(..., description="Market-cap-weighted index level (each ticker rebased to 100)")


class SectorPerformanceMarketStats(BaseModel):
    cumulative_return_pct: Optional[float] = Field(
        None,
        description="Total return over the 1Y window on the market calendar (%)",
    )
    sharpe_ratio: Optional[float] = Field(
        None,
        description="Annualized Sharpe ratio (252-day, risk-free = 0)",
    )
    max_drawdown_pct: Optional[float] = Field(
        None,
        description="Maximum peak-to-trough drawdown over the window (%)",
    )
    calmar_ratio: Optional[float] = Field(
        None,
        description="Calmar ratio: annualized return / |max drawdown|",
    )
    volatility_pct: Optional[float] = Field(
        None,
        description="Annualized daily return volatility (%)",
    )
    trading_days: int = Field(0, description="Trading days in the 1Y window for this market")


class SectorPerformanceResponse(BaseModel):
    level1_id: str
    level2_id: str
    level3_id: str
    scope: str = Field("L3", description="Constituent scope level: L1, L2, or L3")
    as_of: Optional[str] = None
    source: str = "computed"
    stale: bool = False
    window_start: Optional[str] = Field(
        None,
        description="Union window start (earliest market); prefer series_by_market for per-market bounds",
    )
    window_end: Optional[str] = Field(
        None,
        description="Union window end (latest market); prefer series_by_market for per-market bounds",
    )
    points: List[SectorPerformancePoint] = Field(default_factory=list)
    series_by_market: Dict[MarketKey, List[SectorPerformanceMarketPoint]] = Field(
        default_factory=dict,
        description="Per-market index series on each market's own trading calendar (1Y window)",
    )
    stats_by_market: Dict[MarketKey, SectorPerformanceMarketStats] = Field(
        default_factory=dict,
        description="1Y risk/return stats per market on each market's trading calendar",
    )
    members_by_market: Dict[MarketKey, int] = Field(
        default_factory=dict,
        description="Constituent count per market in this scope",
    )
