import type { MarketCode } from '../types/dojoMesh';
import type { SectorPathSelection } from '../types/sectorTaxonomy';

const STORAGE_KEY = 'alphadojo-core-ticker';

export type CoreSectorSource = 'navigation' | 'search';

export interface CoreTickerContext {
  ticker: string;
  market?: MarketCode;
  name_zh?: string;
  name_en?: string;
  sector_source?: CoreSectorSource;
  sector_selection?: SectorPathSelection;
}

export function saveCoreTickerContext(ctx: CoreTickerContext) {
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(ctx));
  window.dispatchEvent(new CustomEvent('alphadojo-core-ticker'));
}

export function readCoreTickerContext(): CoreTickerContext | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CoreTickerContext;
    if (!parsed?.ticker) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function clearCoreTickerContext() {
  sessionStorage.removeItem(STORAGE_KEY);
}
