import type { MarketCode } from '../types/market';

const STORAGE_KEY = 'alphadojo-market-order';
export const DEFAULT_MARKET_ORDER: MarketCode[] = ['us', 'cn', 'hk'];
export type MarketDropSide = 'left' | 'right';

export function isMarketCode(value: unknown): value is MarketCode {
  return value === 'us' || value === 'cn' || value === 'hk';
}

function coerceMarketCode(value: unknown): MarketCode | null {
  if (value === 'sh') return 'cn';
  return isMarketCode(value) ? value : null;
}

export function normalizeMarketOrder(stored: unknown): MarketCode[] {
  if (!Array.isArray(stored)) return [...DEFAULT_MARKET_ORDER];

  const seen = new Set<MarketCode>();
  const ordered: MarketCode[] = [];

  for (const item of stored) {
    const code = coerceMarketCode(item);
    if (!code || seen.has(code)) continue;
    seen.add(code);
    ordered.push(code);
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
  side: MarketDropSide = 'left',
): MarketCode[] {
  if (from === to) return order;
  const next = order.filter((code) => code !== from);
  const toIndex = next.indexOf(to);
  if (toIndex === -1) return order;
  next.splice(side === 'right' ? toIndex + 1 : toIndex, 0, from);
  return normalizeMarketOrder(next);
}
