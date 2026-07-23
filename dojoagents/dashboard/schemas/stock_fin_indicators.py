from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, Field
from dojoagents.dashboard.schemas.freshness import FreshnessSource


class CoreTickerFinIndicatorsResponse(BaseModel):
    ticker: str
    market: str = Field(..., description="Market code: sh, hk, or us")
    report_type: str = Field(..., description="quarter for sh/us, accumulate for hk")
    as_of: Optional[str] = Field(None, description="Latest std_report_date (YYYY-MM-DD)")
    source: FreshnessSource = Field(..., description="Canonical data source or migration alias")
    stale: bool = False
    items: List[dict[str, Any]] = Field(default_factory=list)
