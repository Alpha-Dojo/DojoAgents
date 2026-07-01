import type { MarketCode } from '../types/market';
import type { SectorLevelKey } from '../types/sector';
import type { SectorPathSelection } from '../types/sectorTaxonomy';

function selectionKey(selection: SectorPathSelection): string {
  return `${selection.level1Id}:${selection.level2Id}:${selection.level3Id}`;
}

function tickerKey(market: string | undefined, ticker: string): string {
  return `${market ?? ''}:${ticker}`;
}

export const cacheKeys = {
  sectorTaxonomy: () => 'sector-taxonomy',
  sectorScopeMetrics: (selection: SectorPathSelection) =>
    `sector-scope-metrics:${selectionKey(selection)}`,
  sectorAnalysisBundle: (selection: SectorPathSelection) =>
    `sector-analysis-bundle:${selectionKey(selection)}`,
  sectorScopePerformanceAll: (selection: SectorPathSelection) =>
    `sector-scope-performance-all:${selectionKey(selection)}`,
  sectorConstituents: (selection: SectorPathSelection, scope: SectorLevelKey) =>
    `sector-constituents:v3:${selectionKey(selection)}:${scope}`,
  marketOverview: (
    sectorLimit: number,
    days: number,
    minCapKey: string,
  ) => `dojo-mesh-overview:v2:${sectorLimit}:${days}:${minCapKey}`,
  coreTickerQuote: (market: string | undefined, ticker: string) =>
    `core-ticker-quote:${tickerKey(market, ticker)}`,
  coreTickerKline: (market: string | undefined, ticker: string, interval: string) =>
    `core-ticker-kline:${tickerKey(market, ticker)}:${interval}`,
  coreTickerPeBand: (market: string | undefined, ticker: string) =>
    `core-ticker-pe-band:${tickerKey(market, ticker)}`,
  coreTickerFinIndicators: (market: string | undefined, ticker: string) =>
    `core-ticker-fin-indicators:v6:${tickerKey(market, ticker)}`,
  coreTickerSector: (market: string | undefined, ticker: string) =>
    `core-ticker-sector:${tickerKey(market, ticker)}`,
  coreTickerEvents: (market: string | undefined, ticker: string, pageSize: number) =>
    `core-ticker-events:${tickerKey(market, ticker)}:${pageSize}`,
  coreTickerNews: (market: string | undefined, ticker: string, pageSize: number) =>
    `core-ticker-news:${tickerKey(market, ticker)}:${pageSize}`,
  coreTickerIncome: (market: string | undefined, ticker: string) =>
    `core-ticker-income:${tickerKey(market, ticker)}`,
  coreSectorPeMetrics: (selection: SectorPathSelection) =>
    `core-sector-pe-metrics:${selectionKey(selection)}`,
  folioPortfolios: () => 'folio-portfolios',
  folioPortfolioLite: (portfolioId: string) => `folio-portfolio-lite:${portfolioId}`,
  folioPortfolio: (portfolioId: string, benchmark?: string | null) =>
    `folio-portfolio:${portfolioId}:${benchmark ?? 'default'}`,
};

export type ConstituentsByMarket = Record<MarketCode, import('../types/sector').SectorConstituentItem[]>;
