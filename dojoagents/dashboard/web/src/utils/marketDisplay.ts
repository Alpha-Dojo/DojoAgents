import type { MarketCode } from '../types/market';
import cnFlag from '../assets/images/cn.png';
import hkFlag from '../assets/images/hk.png';
import usFlag from '../assets/images/us.png';

export const MARKET_FLAG_IMAGE: Record<MarketCode, string> = {
  us: usFlag,
  cn: cnFlag,
  hk: hkFlag,
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

export function marketLegalCurrencyLabel(
  t: (key: string, params?: Record<string, string | number>) => string,
  market: MarketCode,
): string {
  return t(`entityPage.${MARKET_LEGAL_CURRENCY_KEY[market]}`);
}
