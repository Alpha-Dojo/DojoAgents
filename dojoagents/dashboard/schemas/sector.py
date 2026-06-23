from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class BilingualText(BaseModel):
    zh: str = Field(..., description="Chinese text")
    en: str = Field(..., description="English text")


class SectorNode(BaseModel):
    sector_id: str = Field(..., description="Sector ID")
    name: BilingualText = Field(..., description="Sector name")
    description: BilingualText = Field(..., description="Sector description")
    level: int = Field(..., description="Sector Level")
    parent_sector_id: str = Field(..., description="Parent Sector ID")


class SectorPath(BaseModel):
    sector_level_1: SectorNode = Field(..., description="Level 1 Sector")
    sector_level_2: SectorNode = Field(..., description="Level 2 Sector")
    sector_level_3: SectorNode = Field(..., description="Level 3 Sector")


class SectorTaxonomyL3Item(BaseModel):
    id: str = Field(..., description="Level-3 sector id")
    name: BilingualText
    definition: Optional[BilingualText] = None


class SectorTaxonomyL2Item(BaseModel):
    id: str = Field(..., description="Level-2 sector id")
    name: BilingualText
    description: Optional[BilingualText] = None
    level_3: List[SectorTaxonomyL3Item] = Field(default_factory=list)


class SectorTaxonomyL1Item(BaseModel):
    id: str = Field(..., description="Level-1 sector id")
    name: BilingualText
    description: Optional[BilingualText] = None
    level_2: List[SectorTaxonomyL2Item] = Field(default_factory=list)


class SectorTaxonomyDocumentResponse(BaseModel):
    version: str = Field("api", description="Taxonomy source version")
    id_scheme: str = Field("sector_id", description="Sector id scheme")
    level_1: List[SectorTaxonomyL1Item] = Field(default_factory=list)
