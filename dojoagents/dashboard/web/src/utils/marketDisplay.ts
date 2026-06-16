import type { MarketCode } from '../types/dojoMesh';

export const MARKET_FLAG: Record<MarketCode, string> = {
  us: '🇺🇸',
  sh: '🇨🇳',
  hk: '🇭🇰',
};

export const MARKET_CODE: Record<MarketCode, string> = {
  us: 'US',
  sh: 'CN',
  hk: 'HK',
};

export function marketFlagCode(market: MarketCode): string {
  return `${MARKET_CODE[market]}`;
}

export type MarketLegalCurrencyKey = 'currencyUs' | 'currencySh' | 'currencyHk';

export const MARKET_LEGAL_CURRENCY_KEY: Record<MarketCode, MarketLegalCurrencyKey> = {
  us: 'currencyUs',
  sh: 'currencySh',
  hk: 'currencyHk',
};
