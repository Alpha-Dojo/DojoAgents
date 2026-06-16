import type { MarketCode } from '../types/dojoMesh';
import type { SectorLevelKey } from '../types/dojoSphere';
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
  sectorScopePerformanceAll: (selection: SectorPathSelection) =>
    `sector-scope-performance-all:${selectionKey(selection)}`,
  sectorConstituents: (selection: SectorPathSelection, scope: SectorLevelKey) =>
    `sector-constituents:${selectionKey(selection)}:${scope}`,
  dojoMeshOverview: (sectorLimit: number) => `dojo-mesh-overview:${sectorLimit}`,
  coreTickerQuote: (market: string | undefined, ticker: string) =>
    `core-ticker-quote:${tickerKey(market, ticker)}`,
  coreTickerKline: (market: string | undefined, ticker: string, interval: string) =>
    `core-ticker-kline:${tickerKey(market, ticker)}:${interval}`,
  coreTickerPeBand: (market: string | undefined, ticker: string) =>
    `core-ticker-pe-band:${tickerKey(market, ticker)}`,
  coreTickerFinIndicators: (market: string | undefined, ticker: string, limit: number) =>
    `core-ticker-fin-indicators:v2:${tickerKey(market, ticker)}:${limit}`,
  coreTickerSector: (market: string | undefined, ticker: string) =>
    `core-ticker-sector:${tickerKey(market, ticker)}`,
  coreTickerEvents: (market: string | undefined, ticker: string, pageSize: number) =>
    `core-ticker-events:${tickerKey(market, ticker)}:${pageSize}`,
  coreTickerNews: (market: string | undefined, ticker: string, pageSize: number) =>
    `core-ticker-news:${tickerKey(market, ticker)}:${pageSize}`,
  coreTickerIncome: (market: string | undefined, ticker: string) =>
    `core-ticker-income:${tickerKey(market, ticker)}`,
  folioPortfolios: () => 'folio-portfolios',
  folioPortfolio: (portfolioId: string) => `folio-portfolio:${portfolioId}`,
};

export type ConstituentsByMarket = Record<MarketCode, import('../types/dojoSphere').SectorConstituentItem[]>;
