import type { SectorLevelKey } from '../types/sector';
import type { SectorPathSelection } from '../types/sectorTaxonomy';

let persistedSelection: SectorPathSelection | null = null;
let persistedScopeLevel: SectorLevelKey = 'L3';

export function readPersistedSectorSelection(): SectorPathSelection | null {
  return persistedSelection;
}

export function readPersistedSectorScopeLevel(): SectorLevelKey {
  return persistedScopeLevel;
}

export function persistSectorViewState(
  selection: SectorPathSelection,
  scopeLevel: SectorLevelKey,
) {
  persistedSelection = selection;
  persistedScopeLevel = scopeLevel;
  window.dispatchEvent(new CustomEvent('alphadojo-sector-selection'));
}

export function clearPersistedSectorViewState() {
  persistedSelection = null;
  persistedScopeLevel = 'L3';
}
