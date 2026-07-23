from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field
from dojoagents.harnesses.built_in.financial.contracts.freshness import FreshnessSource


class CoreIncomeDistributionItem(BaseModel):
    item_name: str
    main_business_income: float
    mbi_ratio: float = Field(..., description="Share of total main business income")


class CoreIncomeDistributionSlice(BaseModel):
    mainop_type: str = Field(..., description="1=industry, 2=product, 3=region")
    report_date: Optional[str] = None
    items: List[CoreIncomeDistributionItem] = Field(default_factory=list)


class CoreTickerIncomeResponse(BaseModel):
    ticker: str
    market: str = Field(..., description="Market code: sh, hk, or us")
    report_date: Optional[str] = Field(None, description="Latest report_date across all slices")
    source: FreshnessSource = Field(..., description="Canonical data source or migration alias")
    stale: bool = False
    distributions: List[CoreIncomeDistributionSlice] = Field(default_factory=list)
