import type { FolioPortfolioDetail } from '../api/folio';

export type FolioCandidatesSortKey =
  | 'price'
  | 'changePercent'
  | 'marketCap'
  | 'pe'
  | 'pb'
  | 'dividendYield'
  | 'eps'
  | 'turnRate';

export type FolioCandidatesSortDir = 'asc' | 'desc';

type CandidateRow = FolioPortfolioDetail['candidates'][number];

function compareNullableNumber(
  a: number | null | undefined,
  b: number | null | undefined,
  dir: FolioCandidatesSortDir,
): number {
  const aMissing = a == null || !Number.isFinite(a);
  const bMissing = b == null || !Number.isFinite(b);
  if (aMissing && bMissing) return 0;
  if (aMissing) return 1;
  if (bMissing) return -1;
  const factor = dir === 'asc' ? 1 : -1;
  return (a - b) * factor;
}

export function sortFolioCandidates(
  rows: CandidateRow[],
  key: FolioCandidatesSortKey,
  dir: FolioCandidatesSortDir,
): CandidateRow[] {
  const factor = dir === 'asc' ? 1 : -1;
  return [...rows].sort((a, b) => {
    let cmp = 0;
    switch (key) {
      case 'price':
        cmp = (a.price - b.price) * factor;
        break;
      case 'changePercent':
        cmp = (a.changePercent - b.changePercent) * factor;
        break;
      case 'marketCap':
        cmp = (a.marketCap - b.marketCap) * factor;
        break;
      case 'pe':
        cmp = compareNullableNumber(a.pe, b.pe, dir);
        break;
      case 'pb':
        cmp = compareNullableNumber(a.pb, b.pb, dir);
        break;
      case 'dividendYield':
        cmp = compareNullableNumber(a.dividendYield, b.dividendYield, dir);
        break;
      case 'eps':
        cmp = compareNullableNumber(a.eps, b.eps, dir);
        break;
      case 'turnRate':
        cmp = compareNullableNumber(a.turnRate, b.turnRate, dir);
        break;
    }
    if (cmp !== 0) return cmp;
    return a.ticker.localeCompare(b.ticker);
  });
}
