import type { MarketCode } from '../types/dojoMesh';

/** A/HK lot size: multiples of 100, minimum 100 when allocated. */
export function normalizeLotShares(rawShares: number, lotSize = 100): number {
  if (rawShares < lotSize * 0.5) return 0;
  if (rawShares < lotSize) return lotSize;
  return Math.round(rawShares / lotSize) * lotSize;
}

export function normalizeManualShares(market: MarketCode, rawValue: number): number {
  if (!Number.isFinite(rawValue) || rawValue <= 0) return 0;
  if (market === 'us') return Math.floor(rawValue);
  return normalizeLotShares(rawValue);
}

export function sharesInputStep(market: MarketCode): number {
  return market === 'us' ? 1 : 100;
}
