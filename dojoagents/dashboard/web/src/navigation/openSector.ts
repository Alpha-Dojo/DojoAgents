import { persistSectorViewState } from '../cache/sectorViewState';
import type { AppTab } from './appTab';
import { clearSectorJumpContext, notifySectorNavigation } from './sectorContext';
import type { SectorLevelKey } from '../types/sector';
import type { SectorPathSelection } from '../types/sectorTaxonomy';
import type { EntitySectorCrumb } from '../types/entity';

export function selectionFromCoreCrumb(crumb: EntitySectorCrumb): SectorPathSelection {
  return {
    level1Id: crumb.level1Id,
    level2Id: crumb.level2Id,
    level3Id: crumb.level3Id,
  };
}

export function openSphereFromSelection(
  onNavigateTab: ((tab: AppTab) => void) | undefined,
  selection: SectorPathSelection,
  scopeLevel: SectorLevelKey,
) {
  if (!onNavigateTab) return;
  clearSectorJumpContext();
  persistSectorViewState(selection, scopeLevel);
  notifySectorNavigation();
  onNavigateTab('sector');
}

export function openSectorFromEntityCrumb(
  onNavigateTab: ((tab: AppTab) => void) | undefined,
  crumb: EntitySectorCrumb,
) {
  openSphereFromSelection(onNavigateTab, selectionFromCoreCrumb(crumb), crumb.level as SectorLevelKey);
}
