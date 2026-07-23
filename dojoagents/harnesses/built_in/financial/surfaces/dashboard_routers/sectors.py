from __future__ import annotations

from fastapi import APIRouter, Depends

from dojoagents.harnesses.built_in.financial.surfaces.dashboard_dependencies import get_sector_store
from dojoagents.harnesses.built_in.financial.services.sector_store import SectorStore
from dojoagents.harnesses.built_in.financial.contracts.sector import SectorTaxonomyDocumentResponse

router = APIRouter(prefix="/sectors", tags=["sectors"])


@router.get("/taxonomy", response_model=SectorTaxonomyDocumentResponse)
async def get_sector_taxonomy(
    store: SectorStore = Depends(get_sector_store),
) -> SectorTaxonomyDocumentResponse:
    """L1/L2/L3 sector tree from cached query_sector_info data."""
    return store.to_taxonomy_document()
