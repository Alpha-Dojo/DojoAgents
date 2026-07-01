import { invalidateCachePrefix } from './queryCache';

/** Prefixes invalidated when backend market/kline data is refreshed. */
export const MARKET_DATA_CACHE_PREFIXES = [
  'core-ticker-',
  'sector-',
  'dojo-mesh-',
  'folio-portfolio:',
] as const;

export const MARKET_DATA_REVISION_EVENT = 'dojo-market-data-revision';

let activeRevision = '';

export function getMarketDataRevision(): string {
  return activeRevision;
}

export function setMarketDataRevision(revision: string) {
  activeRevision = revision;
}

export function invalidateMarketDataCaches() {
  for (const prefix of MARKET_DATA_CACHE_PREFIXES) {
    invalidateCachePrefix(prefix);
  }
}

export function applyMarketDataRevision(revision: string): boolean {
  const normalized = revision.trim();
  if (!normalized || normalized === activeRevision) {
    return false;
  }
  setMarketDataRevision(normalized);
  invalidateMarketDataCaches();
  if (typeof window !== 'undefined') {
    window.dispatchEvent(
      new CustomEvent(MARKET_DATA_REVISION_EVENT, { detail: { revision: normalized } }),
    );
  }
  return true;
}
