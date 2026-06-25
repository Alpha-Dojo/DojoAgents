import type { MarketCode } from '../types/dojoMesh';

function normalizeTickerSymbol(ticker: string): string {
  return ticker.trim().toUpperCase();
}

function shBareSymbol(ticker: string): string {
  return normalizeTickerSymbol(ticker).replace(/\.SS$/, '');
}

function hkBareSymbol(ticker: string): string {
  const upper = normalizeTickerSymbol(ticker).replace(/\.HK$/, '');
  return upper.replace(/^0(?=\d{4}$)/, '');
}

export function tickersMatch(market: MarketCode, left: string, right: string): boolean {
  const a = normalizeTickerSymbol(left);
  const b = normalizeTickerSymbol(right);
  if (a === b) return true;

  if (market === 'cn') {
    return shBareSymbol(a) === shBareSymbol(b);
  }

  if (market === 'hk') {
    return hkBareSymbol(a) === hkBareSymbol(b);
  }

  return false;
}
