import type { MarketCode } from '../types/dojoMesh';

const STORAGE_KEY = 'alphadojo-market-order';
export const DEFAULT_MARKET_ORDER: MarketCode[] = ['us', 'sh', 'hk'];

export function isMarketCode(value: unknown): value is MarketCode {
  return value === 'us' || value === 'sh' || value === 'hk';
}

export function normalizeMarketOrder(stored: unknown): MarketCode[] {
  if (!Array.isArray(stored)) return [...DEFAULT_MARKET_ORDER];

  const seen = new Set<MarketCode>();
  const ordered: MarketCode[] = [];

  for (const item of stored) {
    if (!isMarketCode(item) || seen.has(item)) continue;
    seen.add(item);
    ordered.push(item);
  }

  for (const code of DEFAULT_MARKET_ORDER) {
    if (!seen.has(code)) ordered.push(code);
  }

  return ordered;
}

export function readStoredMarketOrder(): MarketCode[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [...DEFAULT_MARKET_ORDER];
    return normalizeMarketOrder(JSON.parse(raw));
  } catch {
    return [...DEFAULT_MARKET_ORDER];
  }
}

export function storeMarketOrder(order: MarketCode[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(normalizeMarketOrder(order)));
  } catch {
    /* ignore */
  }
}

export function reorderMarkets(
  order: MarketCode[],
  from: MarketCode,
  to: MarketCode,
): MarketCode[] {
  if (from === to) return order;
  const next = order.filter((code) => code !== from);
  const toIndex = next.indexOf(to);
  if (toIndex === -1) return order;
  next.splice(toIndex, 0, from);
  return normalizeMarketOrder(next);
}
