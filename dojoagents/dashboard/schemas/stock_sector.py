from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class BilingualLabel(BaseModel):
    zh: str = ""
    en: str = ""


class SectorLevelPath(BaseModel):
    level_1: BilingualLabel = Field(default_factory=BilingualLabel)
    level_2: BilingualLabel = Field(default_factory=BilingualLabel)
    level_3: BilingualLabel = Field(default_factory=BilingualLabel)


class StockSectorLabel(BaseModel):
    ticker: str = Field(..., description="Stock ticker")
    market: str = Field(..., description="Market code: sh, hk, us")
    primary: SectorLevelPath = Field(default_factory=SectorLevelPath)
    secondary: List[SectorLevelPath] = Field(default_factory=list)
