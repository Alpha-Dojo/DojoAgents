import type { MarketCode } from '../types/dojoMesh';
import type { FolioHolding } from '../types/dojoFolio';
import { INCOME_SLICE_COLORS } from './coreIncomeDistribution';

export interface FolioSectorSlice {
  key: string;
  name: string;
  value: number;
  color: string;
  ratio: number;
  returnPercent: number;
}

export function prepareFolioSectorSlices(
  holdings: FolioHolding[],
  market: MarketCode,
): FolioSectorSlice[] {
  const marketHoldings = holdings.filter((row) => row.market === market && row.marketValue > 0);
  if (!marketHoldings.length) return [];

  const bySector = new Map<string, FolioHolding[]>();
  for (const row of marketHoldings) {
    const bucket = bySector.get(row.sector) ?? [];
    bucket.push(row);
    bySector.set(row.sector, bucket);
  }

  const totalValue = marketHoldings.reduce((sum, row) => sum + row.marketValue, 0);
  if (totalValue <= 0) return [];

  const rows = [...bySector.entries()]
    .map(([name, sectorHoldings]) => {
      const value = sectorHoldings.reduce((sum, row) => sum + row.marketValue, 0);
      const cost = sectorHoldings.reduce((sum, row) => sum + row.shares * row.cost, 0);
      const returnPercent = cost > 0 ? ((value - cost) / cost) * 100 : 0;
      return { name, value, returnPercent };
    })
    .sort((a, b) => b.value - a.value);

  return rows.map((row, index) => ({
    key: `${market}:${row.name}:${index}`,
    name: row.name,
    value: row.value,
    color: INCOME_SLICE_COLORS[index % INCOME_SLICE_COLORS.length],
    ratio: row.value / totalValue,
    returnPercent: row.returnPercent,
  }));
}

export function marketHoldingsTotal(holdings: FolioHolding[], market: MarketCode): number {
  return holdings
    .filter((row) => row.market === market)
    .reduce((sum, row) => sum + row.marketValue, 0);
}
