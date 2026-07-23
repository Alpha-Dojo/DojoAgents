from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, Field
from dojoagents.harnesses.built_in.financial.contracts.freshness import FreshnessSource


class CoreTickerNewsResponse(BaseModel):
    ticker: str
    market: str = Field(..., description="Market code: sh, hk, or us")
    as_of: Optional[str] = Field(None, description="Latest news publish date (YYYY-MM-DD)")
    source: FreshnessSource = Field(..., description="Canonical data source or migration alias")
    stale: bool = False
    items: List[dict[str, Any]] = Field(default_factory=list)
