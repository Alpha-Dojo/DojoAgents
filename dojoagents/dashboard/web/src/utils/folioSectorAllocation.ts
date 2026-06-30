import type { MarketCode } from '../types/market';
import type { FolioHolding } from '../types/folio';
import { INCOME_SLICE_COLORS } from './entityIncomeDistribution';

export type FolioSectorLevel = 'L1' | 'L2' | 'L3';

export interface FolioSectorSlice {
  key: string;
  name: string;
  value: number;
  color: string;
  ratio: number;
  returnPercent: number;
}

const OTHER_SECTOR = '其他';

function sectorNameForLevel(holding: FolioHolding, level: FolioSectorLevel): string {
  const raw =
    level === 'L1'
      ? holding.sectorL1 ?? holding.sector
      : level === 'L2'
        ? holding.sectorL2 ?? holding.sector
        : holding.sectorL3 ?? holding.sector;
  const trimmed = raw?.trim();
  return trimmed || OTHER_SECTOR;
}

export function prepareFolioSectorSlices(
  holdings: FolioHolding[],
  market: MarketCode,
  level: FolioSectorLevel = 'L1',
): FolioSectorSlice[] {
  const marketHoldings = holdings.filter((row) => row.market === market && row.marketValue > 0);
  if (!marketHoldings.length) return [];

  const bySector = new Map<string, FolioHolding[]>();
  for (const row of marketHoldings) {
    const name = sectorNameForLevel(row, level);
    const bucket = bySector.get(name) ?? [];
    bucket.push(row);
    bySector.set(name, bucket);
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
    key: `${market}:${level}:${row.name}:${index}`,
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
