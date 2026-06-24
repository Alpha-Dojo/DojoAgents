import type { MarketCode } from '../types/dojoMesh';

export const MARKET_FLAG: Record<MarketCode, string> = {
  us: '🇺🇸',
  cn: '🇨🇳',
  hk: '🇭🇰',
};

export const MARKET_CODE: Record<MarketCode, string> = {
  us: 'US',
  cn: 'CN',
  hk: 'HK',
};

export function marketFlagCode(market: MarketCode): string {
  return `${MARKET_CODE[market]}`;
}

export type MarketLegalCurrencyKey = 'currencyUs' | 'currencySh' | 'currencyHk';

export const MARKET_LEGAL_CURRENCY_KEY: Record<MarketCode, MarketLegalCurrencyKey> = {
  us: 'currencyUs',
  cn: 'currencySh',
  hk: 'currencyHk',
};
