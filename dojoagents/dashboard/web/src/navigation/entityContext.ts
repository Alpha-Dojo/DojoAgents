import type { MarketCode } from '../types/market';
import type { SectorPathSelection } from '../types/sectorTaxonomy';

const STORAGE_KEY = 'alphadojo-entity-ticker';

export type EntitySectorSource = 'navigation' | 'search';

export interface EntityTickerContext {
  ticker: string;
  market?: MarketCode;
  name_zh?: string;
  name_en?: string;
  sector_source?: EntitySectorSource;
  sector_selection?: SectorPathSelection;
}

/** Fallback when no ticker was chosen from Mesh/Sphere (largest US market cap as of 2025). */
export const DEFAULT_ENTITY_TICKER: EntityTickerContext = {
  ticker: 'NVDA',
  market: 'us',
  name_en: 'NVIDIA Corporation',
  name_zh: '英伟达',
  sector_source: 'search',
};

export function saveEntityTickerContext(ctx: EntityTickerContext) {
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(ctx));
  window.dispatchEvent(new CustomEvent('alphadojo-entity-ticker'));
}

export function readEntityTickerContext(): EntityTickerContext | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as EntityTickerContext;
    if (!parsed?.ticker) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function clearEntityTickerContext() {
  sessionStorage.removeItem(STORAGE_KEY);
}

/** Read saved ticker or seed session with the default largest-cap symbol. */
export function resolveEntityTickerContext(): EntityTickerContext {
  const saved = readEntityTickerContext();
  if (saved) return saved;
  saveEntityTickerContext(DEFAULT_ENTITY_TICKER);
  return DEFAULT_ENTITY_TICKER;
}
