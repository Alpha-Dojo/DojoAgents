import type { FolioPortfolioDetail } from '../api/folio';
import { FOLIO_MARKETS } from '../types/folio';
import type { MarketCode } from '../types/market';
import { computeFolioHeadlineMetrics } from './folioHeadlineMetrics';

export interface FolioMarketSnapshot {
  todayChange: number | null;
  netValue: number | null;
  totalReturn: number | null;
  candidateCount: number;
  holdingCount: number;
}

export type FolioMarketSnapshotsByMarket = Record<MarketCode, FolioMarketSnapshot>;

function countByMarket<T extends { market: MarketCode }>(rows: T[]): Record<MarketCode, number> {
  const counts: Record<MarketCode, number> = { us: 0, cn: 0, hk: 0 };
  for (const row of rows) {
    counts[row.market] += 1;
  }
  return counts;
}

export function emptyMarketSnapshots(): FolioMarketSnapshotsByMarket {
  return FOLIO_MARKETS.reduce((acc, market) => {
    acc[market] = {
      todayChange: 0,
      netValue: null,
      totalReturn: 0,
      candidateCount: 0,
      holdingCount: 0,
    };
    return acc;
  }, {} as FolioMarketSnapshotsByMarket);
}

/** Sidebar per-market stats — aligned with FolioHeadlineMetrics / center panel cards. */
export function computeMarketSnapshotsFromDetail(
  detail: FolioPortfolioDetail,
): FolioMarketSnapshotsByMarket {
  const headline = computeFolioHeadlineMetrics(detail);
  const candidateCount = countByMarket(detail.candidates);
  const holdingCount = countByMarket(
    detail.positions.filter((row) => row.shares > 0),
  );

  return FOLIO_MARKETS.reduce((acc, market) => {
    const row = headline.byMarket.find((item) => item.market === market);
    const holdings = holdingCount[market];
    acc[market] = {
      todayChange: holdings > 0 ? row?.todayPnlPct ?? 0 : 0,
      netValue: row?.assets ?? null,
      totalReturn: holdings > 0 ? row?.totalPnlPct ?? 0 : 0,
      candidateCount: candidateCount[market],
      holdingCount: holdings,
    };
    return acc;
  }, {} as FolioMarketSnapshotsByMarket);
}
