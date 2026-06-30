import type { FolioPortfolioDetail } from '../api/folio';
import { FOLIO_MARKETS } from '../types/folio';
import type { MarketCode } from '../types/market';

export interface FolioHeadlineMarketRow {
  market: MarketCode;
  assets: number | null;
  totalPnlPct: number;
  todayPnlPct: number;
}

export interface FolioHeadlineMetricsView {
  byMarket: FolioHeadlineMarketRow[];
}

function marketAssets(detail: FolioPortfolioDetail, market: MarketCode): number | null {
  const net = detail.netValueByMarket[market] ?? 0;
  if (net > 0) return net;

  const positions = detail.positions.filter((row) => row.market === market);
  if (positions.length > 0) {
    const sum = positions.reduce((acc, row) => acc + row.marketValue, 0);
    if (sum > 0) return sum;
  }

  const capital = detail.config?.capitalByMarket[market] ?? 0;
  return capital > 0 ? capital : null;
}

function marketHasHoldings(detail: FolioPortfolioDetail, market: MarketCode): boolean {
  return detail.positions.some((row) => row.market === market && row.shares > 0);
}

function marketTodayPnl(detail: FolioPortfolioDetail, market: MarketCode): number {
  if (!marketHasHoldings(detail, market)) return 0;

  const positions = detail.positions.filter(
    (row) => row.market === market && row.shares > 0,
  );
  const netValue = positions.reduce((acc, row) => acc + row.marketValue, 0);
  if (netValue <= 0) return 0;
  return positions.reduce((acc, row) => acc + row.changePercent * row.marketValue, 0) / netValue;
}

function marketTotalPnlPct(detail: FolioPortfolioDetail, market: MarketCode): number {
  if (!marketHasHoldings(detail, market)) return 0;

  const capital = detail.config?.capitalByMarket[market] ?? 0;
  const net = detail.netValueByMarket[market] ?? 0;
  if (capital > 0 && net > 0) {
    return ((net - capital) / capital) * 100;
  }

  return detail.performance?.statsByMarket?.[market]?.cumulative_return_pct ?? 0;
}

export function computeFolioHeadlineMetrics(detail: FolioPortfolioDetail): FolioHeadlineMetricsView {
  return {
    byMarket: FOLIO_MARKETS.map((market) => ({
      market,
      assets: marketAssets(detail, market),
      totalPnlPct: marketTotalPnlPct(detail, market),
      todayPnlPct: marketTodayPnl(detail, market),
    })),
  };
}
