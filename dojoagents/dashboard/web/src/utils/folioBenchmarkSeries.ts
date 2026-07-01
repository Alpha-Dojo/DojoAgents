import type { BenchmarkCatalogResponse } from '../api/market';
import type { BenchmarkCard, MarketCode } from '../types/market';
import type { FolioPerformanceView } from '../types/folio';
import { FOLIO_MARKETS } from '../types/folio';
import {
  parseFolioCandidateIndexSymbol,
  resolveFolioBenchmarkLabel,
} from './folioCandidateIndex';
import {
  alignMarketSeriesToMasterDates,
  lookupMarketValueOnOrBefore,
  rebaseMarketSeries,
  type MarketSeriesPoint,
} from './sectorPerformanceSeries';

export type FolioBenchmarkOption = {
  market: MarketCode;
  symbol: string;
  labelZh: string;
  labelEn: string;
};

export interface FolioBenchmarkHeadChip {
  symbol: string;
  market: MarketCode;
  label: string;
  date: string;
  value: number;
}

function benchmarkName(card: BenchmarkCard): { zh: string; en: string } {
  if (typeof card.name === 'string') {
    return { zh: card.name, en: card.name };
  }
  return {
    zh: card.name?.zh || card.name?.en || card.symbol,
    en: card.name?.en || card.name?.zh || card.symbol,
  };
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
      const names = benchmarkName(item);
      options.push({
        market,
        symbol: item.symbol,
        labelZh: names.zh,
        labelEn: names.en,
      });
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

function benchmarkSeriesForMasterDates(
  raw: MarketSeriesPoint[],
  masterDates: string[],
): MarketSeriesPoint[] | null {
  if (raw.length < 2 || masterDates.length < 2) return null;
  const aligned = alignMarketSeriesToMasterDates(masterDates, raw);
  const rebased = rebaseMarketSeries(aligned);
  return rebased.length >= 2 ? rebased : null;
}

export function rebaseBenchmarkSeriesForDates(
  masterDates: string[],
  card: BenchmarkCard,
): MarketSeriesPoint[] | null {
  return benchmarkSeriesForMasterDates(benchmarkCardToSeries(card), masterDates);
}

export function buildRebasedBenchmarkSeriesBySymbol(
  symbols: string[],
  catalog: BenchmarkCatalogResponse | null,
  masterDates: string[],
  performance?: FolioPerformanceView | null,
): Record<string, MarketSeriesPoint[]> {
  const result: Record<string, MarketSeriesPoint[]> = {};
  for (const symbol of symbols) {
    const candidateMarket = parseFolioCandidateIndexSymbol(symbol);
    if (candidateMarket) {
      const raw = performance?.candidateSeriesByMarket?.[candidateMarket];
      if (raw?.length && raw.length >= 2) {
        const series = benchmarkSeriesForMasterDates(raw, masterDates);
        if (series) result[symbol] = series;
      }
      continue;
    }
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
  labelForMarket?: (market: MarketCode) => string,
  locale: 'zh' | 'en' = 'en',
): FolioBenchmarkHeadChip[] {
  return symbols.flatMap((symbol) => {
    const series = rebasedBySymbol[symbol];
    if (!series?.length) return [];
    const option = findFolioBenchmarkOption(catalog, symbol);
    const candidateMarket = parseFolioCandidateIndexSymbol(symbol);
    const label = resolveFolioBenchmarkLabel(
      symbol,
      option,
      labelForMarket ?? ((market) => market.toUpperCase()),
      locale,
    );
    const market = candidateMarket ?? option?.market;
    if (!market) return [];
    const point = anchorDate
      ? lookupMarketValueOnOrBefore(series, anchorDate)
      : series[series.length - 1];
    if (!point) return [];
    return [
      {
        symbol,
        market,
        label,
        date: point.date,
        value: point.value,
      },
    ];
  });
}
