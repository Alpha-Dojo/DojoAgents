import type { FolioHolding } from '../types/folio';
import { FOLIO_MARKETS } from '../types/folio';
import type { MarketCode } from '../types/market';

export interface FolioMarketSnapshot {
  todayChange: number | null;
  netValue: number;
  totalReturn: number | null;
  holdingCount: number;
}

export interface FolioSnapshotOptions {
  netValueByMarket?: Partial<Record<MarketCode, number>>;
  costBasisByMarket?: Partial<Record<MarketCode, number>>;
  /** When present, sidebar total return matches the NAV performance table. */
  returnPctByMarket?: Partial<Record<MarketCode, number>>;
}

export function computeMarketSnapshots(
  holdings: FolioHolding[],
  options?: FolioSnapshotOptions,
): Partial<Record<MarketCode, FolioMarketSnapshot>> {
  const byMarket: Record<MarketCode, FolioHolding[]> = { us: [], cn: [], hk: [] };
  for (const row of holdings) {
    byMarket[row.market].push(row);
  }

  const result: Partial<Record<MarketCode, FolioMarketSnapshot>> = {};
  for (const market of FOLIO_MARKETS) {
    const rows = byMarket[market];
    if (rows.length === 0) continue;

    const netValueFromApi = options?.netValueByMarket?.[market];
    const netValue =
      netValueFromApi != null && netValueFromApi > 0
        ? netValueFromApi
        : rows.reduce((sum, row) => sum + row.marketValue, 0);

    let todayChange: number | null = null;
    if (netValue > 0) {
      todayChange =
        rows.reduce((sum, row) => sum + row.changePercent * row.marketValue, 0) / netValue;
    }

    const totalReturn =
      options?.returnPctByMarket?.[market] ?? null;

    result[market] = { todayChange, netValue, totalReturn, holdingCount: rows.length };
  }

  return result;
}

export function marketsWithSnapshots(
  snapshots: Partial<Record<MarketCode, FolioMarketSnapshot>> | undefined,
): MarketCode[] {
  if (!snapshots) return [];
  return FOLIO_MARKETS.filter((market) => snapshots[market] != null);
}
