import type { MarketCode } from '../types/dojoMesh';
import { formatFolioCurrency } from './folioFormat';

function marketCurrency(market: MarketCode): string {
  if (market === 'sh') return 'CNY';
  if (market === 'hk') return 'HKD';
  return 'USD';
}

export function formatMarketNetValue(market: MarketCode, value: number): string {
  return formatFolioCurrency(value, marketCurrency(market));
}
