import type { BenchmarkCatalogResponse } from '../api/market';
import type { BenchmarkCard, MarketCode } from '../types/market';
import { FOLIO_MARKETS } from '../types/folio';
import {
  alignMarketSeriesToMasterDates,
  lookupMarketValueOnOrBefore,
  rebaseMarketSeries,
  type MarketSeriesPoint,
} from './sectorPerformanceSeries';

export type FolioBenchmarkOption = {
  market: MarketCode;
  symbol: string;
  label: string;
};

export interface FolioBenchmarkHeadChip {
  symbol: string;
  market: MarketCode;
  label: string;
  date: string;
  value: number;
}

export function flattenFolioBenchmarkOptions(
  catalog: BenchmarkCatalogResponse | null,
): FolioBenchmarkOption[] {
  if (!catalog) return [];
  const options: FolioBenchmarkOption[] = [];
  for (const market of FOLIO_MARKETS) {
    const group = catalog.markets[market];
    if (!group) continue;
    for (const item of group.benchmarks) {
      const label =
        typeof item.name === 'string'
          ? item.name
          : item.name?.zh || item.name?.en || item.symbol;
      options.push({ market, symbol: item.symbol, label });
    }
  }
  return options;
}

export function findFolioBenchmarkCard(
  catalog: BenchmarkCatalogResponse | null,
  symbol: string,
): BenchmarkCard | null {
  if (!catalog) return null;
  for (const market of FOLIO_MARKETS) {
    const card = catalog.markets[market]?.benchmarks.find((item) => item.symbol === symbol);
    if (card) return card;
  }
  return null;
}

export function findFolioBenchmarkOption(
  catalog: BenchmarkCatalogResponse | null,
  symbol: string,
): FolioBenchmarkOption | null {
  return flattenFolioBenchmarkOptions(catalog).find((item) => item.symbol === symbol) ?? null;
}

function benchmarkCardToSeries(card: BenchmarkCard): MarketSeriesPoint[] {
  return card.kline
    .map((bar) => ({
      date: bar.datetime.slice(0, 10),
      value: Number(bar.close),
    }))
    .filter((point) => point.date && Number.isFinite(point.value));
}

export function rebaseBenchmarkSeriesForDates(
  masterDates: string[],
  card: BenchmarkCard,
): MarketSeriesPoint[] | null {
  const raw = benchmarkCardToSeries(card);
  if (raw.length < 2 || masterDates.length < 2) return null;
  const rebased = rebaseMarketSeries(raw);
  const aligned = alignMarketSeriesToMasterDates(masterDates, rebased);
  return aligned.length >= 2 ? aligned : null;
}

export function buildRebasedBenchmarkSeriesBySymbol(
  symbols: string[],
  catalog: BenchmarkCatalogResponse | null,
  masterDates: string[],
): Record<string, MarketSeriesPoint[]> {
  const result: Record<string, MarketSeriesPoint[]> = {};
  for (const symbol of symbols) {
    const card = findFolioBenchmarkCard(catalog, symbol);
    if (!card) continue;
    const series = rebaseBenchmarkSeriesForDates(masterDates, card);
    if (series) result[symbol] = series;
  }
  return result;
}

export function buildFolioBenchmarkHeadChips(
  symbols: string[],
  catalog: BenchmarkCatalogResponse | null,
  rebasedBySymbol: Record<string, MarketSeriesPoint[]>,
  anchorDate?: string | null,
): FolioBenchmarkHeadChip[] {
  return symbols.flatMap((symbol) => {
    const series = rebasedBySymbol[symbol];
    const option = findFolioBenchmarkOption(catalog, symbol);
    if (!series?.length || !option) return [];
    const point = anchorDate
      ? lookupMarketValueOnOrBefore(series, anchorDate)
      : series[series.length - 1];
    if (!point) return [];
    return [
      {
        symbol,
        market: option.market,
        label: option.label,
        date: point.date,
        value: point.value,
      },
    ];
  });
}
