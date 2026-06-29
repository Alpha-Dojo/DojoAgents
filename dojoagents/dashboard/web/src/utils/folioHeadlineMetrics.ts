import type { FolioPortfolioDetail } from '../api/folio';
import type { FolioPerformanceView } from '../types/folio';
import { FOLIO_MARKETS } from '../types/folio';
import type { MarketCode } from '../types/market';
import { resolveBenchmarkStats } from './folioPerformanceStats';

export interface FolioHeadlineMetricValue {
  pct: number | null;
  usd: number | null;
}

export interface FolioHeadlineMetricsView {
  alpha: FolioHeadlineMetricValue;
  totalPnl: FolioHeadlineMetricValue;
  dailyDelta: number | null;
}

function weightedCumulativeReturn(
  performance: FolioPerformanceView | null | undefined,
  netValueByMarket: Partial<Record<MarketCode, number>>,
): number | null {
  if (!performance) return null;

  let totalWeight = 0;
  let weightedSum = 0;
  for (const market of FOLIO_MARKETS) {
    const weight = netValueByMarket[market] ?? 0;
    const pct = performance.statsByMarket?.[market]?.cumulative_return_pct;
    if (weight <= 0 || pct == null || Number.isNaN(pct)) continue;
    totalWeight += weight;
    weightedSum += pct * weight;
  }
  if (totalWeight <= 0) return null;
  return weightedSum / totalWeight;
}

function sumCostBasisUsd(detail: FolioPortfolioDetail): number | null {
  const { costBasisByMarket } = detail;
  const total = FOLIO_MARKETS.reduce((sum, market) => sum + (costBasisByMarket[market] ?? 0), 0);
  return total > 0 ? total : null;
}

export function computeFolioHeadlineMetrics(
  detail: FolioPortfolioDetail,
  benchmarkSymbol: string | null,
): FolioHeadlineMetricsView {
  const portfolioReturn = weightedCumulativeReturn(detail.performance, detail.netValueByMarket);
  const benchmarkReturn = resolveBenchmarkStats(detail.performance, benchmarkSymbol)?.cumulative_return_pct ?? null;

  const costBasisUsd = sumCostBasisUsd(detail);
  const netValueUsd = detail.netValueUsd;
  const totalPnlUsd =
    netValueUsd != null && costBasisUsd != null ? netValueUsd - costBasisUsd : null;

  const alphaPct =
    portfolioReturn != null && benchmarkReturn != null
      ? portfolioReturn - benchmarkReturn
      : null;
  const alphaUsd =
    alphaPct != null && costBasisUsd != null
      ? (costBasisUsd * alphaPct) / 100
      : null;

  return {
    alpha: { pct: alphaPct, usd: alphaUsd },
    totalPnl: { pct: portfolioReturn, usd: totalPnlUsd },
    dailyDelta: detail.todayChange,
  };
}
