import type { SectorLevelKey } from '../types/dojoSphere';
import type { SectorPathSelection } from '../types/sectorTaxonomy';

let persistedSelection: SectorPathSelection | null = null;
let persistedScopeLevel: SectorLevelKey = 'L3';

export function readPersistedSphereSelection(): SectorPathSelection | null {
  return persistedSelection;
}

export function readPersistedSphereScopeLevel(): SectorLevelKey {
  return persistedScopeLevel;
}

export function persistSphereViewState(
  selection: SectorPathSelection,
  scopeLevel: SectorLevelKey,
) {
  persistedSelection = selection;
  persistedScopeLevel = scopeLevel;
}

export function clearPersistedSphereViewState() {
  persistedSelection = null;
  persistedScopeLevel = 'L3';
}
