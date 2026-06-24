from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class MarketStats(BaseModel):
    """Aggregate market statistics for one exchange."""

    market: str = Field(..., description="Market code: sh, hk, us")
    listed_count: int = Field(
        ...,
        description="Loaded tickers after skipping no_name and no_quote",
    )
    total_market_cap: float = Field(..., description="Sum of market cap (quoted stocks)")
    weighted_pe: Optional[float] = Field(
        None,
        description="Aggregate PE: total_market_cap / sum(cap/pe) for pe>0 (earnings-weighted)",
    )
    simple_pe: Optional[float] = Field(
        None,
        description="Arithmetic mean PE for stocks with pe>0",
    )
    pe_sample_count: int = Field(
        ...,
        description="Number of stocks with valid positive PE used in PE stats",
    )
