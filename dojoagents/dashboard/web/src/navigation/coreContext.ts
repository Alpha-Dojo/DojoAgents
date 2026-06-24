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

/** Fallback when no ticker was chosen from Mesh/Sphere (largest US market cap as of 2025). */
export const DEFAULT_CORE_TICKER: CoreTickerContext = {
  ticker: 'NVDA',
  market: 'us',
  name_en: 'NVIDIA Corporation',
  name_zh: '英伟达',
  sector_source: 'search',
};

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

/** Read saved ticker or seed session with the default largest-cap symbol. */
export function resolveCoreTickerContext(): CoreTickerContext {
  const saved = readCoreTickerContext();
  if (saved) return saved;
  saveCoreTickerContext(DEFAULT_CORE_TICKER);
  return DEFAULT_CORE_TICKER;
}
