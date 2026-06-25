import type { FolioPortfolioDetail } from '../api/dojoFolio';

export type FolioHoldingsSortKey = 'openDate' | 'weight' | 'changePercent' | 'totalReturnPct';
export type FolioHoldingsSortDir = 'asc' | 'desc';

type HoldingRow = FolioPortfolioDetail['holdings'][number];

function openDateValue(row: HoldingRow, portfolioOpenDate: string): number {
  const raw = row.openDate ?? portfolioOpenDate;
  const parsed = Date.parse(raw);
  return Number.isFinite(parsed) ? parsed : 0;
}

function compareNullableNumber(
  a: number | null | undefined,
  b: number | null | undefined,
  dir: FolioHoldingsSortDir,
): number {
  const aMissing = a == null || !Number.isFinite(a);
  const bMissing = b == null || !Number.isFinite(b);
  if (aMissing && bMissing) return 0;
  if (aMissing) return 1;
  if (bMissing) return -1;
  const factor = dir === 'asc' ? 1 : -1;
  return (a - b) * factor;
}

export function sortFolioHoldings(
  rows: HoldingRow[],
  key: FolioHoldingsSortKey,
  dir: FolioHoldingsSortDir,
  portfolioOpenDate: string,
): HoldingRow[] {
  const factor = dir === 'asc' ? 1 : -1;
  return [...rows].sort((a, b) => {
    let cmp = 0;
    switch (key) {
      case 'openDate':
        cmp = (openDateValue(a, portfolioOpenDate) - openDateValue(b, portfolioOpenDate)) * factor;
        break;
      case 'weight':
        cmp = (a.weight - b.weight) * factor;
        break;
      case 'changePercent':
        cmp = (a.changePercent - b.changePercent) * factor;
        break;
      case 'totalReturnPct':
        cmp = compareNullableNumber(a.totalReturnPct, b.totalReturnPct, dir);
        break;
    }
    if (cmp !== 0) return cmp;
    return a.ticker.localeCompare(b.ticker);
  });
}
