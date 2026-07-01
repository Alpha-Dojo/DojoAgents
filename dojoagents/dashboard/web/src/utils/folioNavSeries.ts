import type { FolioPerformancePoint, FolioPerformanceStats, FolioPerformanceView } from '../types/folio';
import type { MarketCode } from '../types/market';
import { FOLIO_MARKETS } from '../types/folio';

/** Order-based NAV when present; otherwise equal-weight candidate pool index (no holdings yet). */
export function resolveFolioChartSeriesByMarket(
  performance: FolioPerformanceView | null | undefined,
): Partial<Record<MarketCode, FolioPerformancePoint[]>> {
  if (!performance) return {};

  const resolved: Partial<Record<MarketCode, FolioPerformancePoint[]>> = {};
  for (const market of FOLIO_MARKETS) {
    const orderSeries = performance.seriesByMarket[market];
    const candidateSeries = performance.candidateSeriesByMarket?.[market];
    if (orderSeries && orderSeries.length >= 2) {
      resolved[market] = orderSeries;
    } else if (candidateSeries && candidateSeries.length >= 2) {
      resolved[market] = candidateSeries;
    }
  }
  return resolved;
}

export function resolveFolioStatsByMarket(
  performance: FolioPerformanceView | null | undefined,
): Partial<Record<MarketCode, FolioPerformanceStats>> {
  if (!performance) return {};

  const resolved: Partial<Record<MarketCode, FolioPerformanceStats>> = {};
  for (const market of FOLIO_MARKETS) {
    const orderStats = performance.statsByMarket?.[market];
    const candidateStats = performance.candidateStatsByMarket?.[market];
    if (orderStats) {
      resolved[market] = orderStats;
    } else if (candidateStats) {
      resolved[market] = candidateStats;
    }
  }
  return resolved;
}

export function folioHasNavPerformance(performance: FolioPerformanceView | null | undefined): boolean {
  return FOLIO_MARKETS.some(
    (market) => (resolveFolioChartSeriesByMarket(performance)[market]?.length ?? 0) >= 2,
  );
}
