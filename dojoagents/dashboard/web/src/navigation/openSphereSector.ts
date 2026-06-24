import { persistSphereViewState } from '../cache/sphereViewState';
import type { AppTab } from './appTab';
import { clearSphereSectorContext, notifySphereNavigation } from './sphereContext';
import type { SectorLevelKey } from '../types/dojoSphere';
import type { SectorPathSelection } from '../types/sectorTaxonomy';
import type { CoreSectorCrumb } from '../types/dojoCore';

export function selectionFromCoreCrumb(crumb: CoreSectorCrumb): SectorPathSelection {
  return {
    level1Id: crumb.level1Id,
    level2Id: crumb.level2Id,
    level3Id: crumb.level3Id,
  };
}

export function openSphereFromCoreCrumb(
  onNavigateTab: ((tab: AppTab) => void) | undefined,
  crumb: CoreSectorCrumb,
) {
  if (!onNavigateTab) return;
  clearSphereSectorContext();
  persistSphereViewState(selectionFromCoreCrumb(crumb), crumb.level as SectorLevelKey);
  notifySphereNavigation();
  onNavigateTab('sphere');
}
