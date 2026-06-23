from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class BilingualText(BaseModel):
    zh: str = ""
    en: str = ""


class SectorMemberItem(BaseModel):
    ticker: str = Field(..., description="Member ticker")
    name: BilingualText = Field(default_factory=BilingualText, description="Display name")
    last_price: float = Field(0.0, description="Latest price")
    market_cap: float = Field(0.0, description="Market capitalization")
    change_percent: float = Field(..., description="Daily change percent")


class SectorItem(BaseModel):
    concept_code: str = Field(..., description="Stable sector identifier")
    name: BilingualText = Field(..., description="Level-3 sector name")
    change_percent: float = Field(
        ...,
        description="Earnings-weighted avg daily change from live stock quotes",
    )
    avg_market_cap: float = Field(0.0, description="Average market cap of members")
    strength: float = Field(..., description="0-100 bar width by avg market cap × change percent")
    sample_tickers: List[str] = Field(default_factory=list, description="Up to 3 member tickers")
    member_count: int = Field(0, description="Total constituent count")
    members: List[SectorMemberItem] = Field(
        default_factory=list,
        description="Constituents sorted by change (desc for gainers context)",
    )


class MarketSectorLead(BaseModel):
    gainers: List[SectorItem] = Field(default_factory=list)
    losers: List[SectorItem] = Field(default_factory=list)


class DojoMeshSectorsResponse(BaseModel):
    markets: dict[str, MarketSectorLead] = Field(default_factory=dict)


class CrossMarketSectorLookupResponse(BaseModel):
    link_key: str = Field(..., description="Level-3 slug shared across markets")
    markets: Dict[str, Optional[SectorItem]] = Field(default_factory=dict)
