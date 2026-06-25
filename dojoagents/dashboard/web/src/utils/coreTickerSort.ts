import type { MarketCode } from '../types/dojoMesh';
import type { CoreTickerSearchItem } from '../types/dojoCore';

const MARKET_ORDER: Record<MarketCode, number> = {
  us: 0,
  cn: 1,
  hk: 2,
};

/** US → A-share → HK, then market cap descending within each market. */
export function sortCoreTickerItems(items: CoreTickerSearchItem[]): CoreTickerSearchItem[] {
  return [...items].sort((a, b) => {
    const byMarket = MARKET_ORDER[a.market] - MARKET_ORDER[b.market];
    if (byMarket !== 0) return byMarket;
    return b.market_cap - a.market_cap;
  });
}
