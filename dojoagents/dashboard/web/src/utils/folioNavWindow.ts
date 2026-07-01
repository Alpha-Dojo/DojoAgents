import type { MarketCode } from '../types/market';
import {
  PERFORMANCE_MARKETS,
  pickMasterMarketSeries,
  rebaseMarketSeries,
  sliceMarketSeriesByDateRange,
  type MarketSeriesPoint,
} from './sectorPerformanceSeries';

export type FolioNavWindowPreset = '3m' | '6m' | '1y' | 'all';

const PRESET_MONTHS: Record<Exclude<FolioNavWindowPreset, 'all'>, number> = {
  '3m': 3,
  '6m': 6,
  '1y': 12,
};

function formatIsoDate(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export function resolveNavWindowStartDate(
  endDate: string,
  preset: FolioNavWindowPreset,
): string | null {
  if (preset === 'all') return null;
  const cursor = new Date(`${endDate}T12:00:00`);
  cursor.setMonth(cursor.getMonth() - PRESET_MONTHS[preset]);
  return formatIsoDate(cursor);
}

function latestSeriesEndDate(
  rebasedByMarket: Partial<Record<MarketCode, MarketSeriesPoint[]>>,
  markets: MarketCode[] = PERFORMANCE_MARKETS,
): string | null {
  const ends = markets.flatMap((market) => {
    const series = rebasedByMarket[market];
    if (!series?.length) return [];
    return [series[series.length - 1].date];
  });
  if (!ends.length) return null;
  return ends.sort().at(-1) ?? null;
}

function sliceMarketWindow(
  series: MarketSeriesPoint[],
  startDate: string | null,
  endDate: string,
): MarketSeriesPoint[] {
  if (!startDate) return series;
  const sliced = sliceMarketSeriesByDateRange(series, startDate, endDate);
  if (sliced.length >= 2) return sliced;

  const startIndex = series.findIndex((point) => point.date >= startDate);
  if (startIndex < 0) {
    return series.length >= 2 ? series.slice(-2) : series;
  }
  const tail = series.slice(startIndex);
  return tail.length >= 2 ? tail : series.length >= 2 ? series.slice(-2) : series;
}

/** Rebase each market NAV so the window's first trading day is 0.00% (index 100). */
export function buildWindowRebasedByMarket(
  rebasedByMarket: Partial<Record<MarketCode, MarketSeriesPoint[]>>,
  preset: FolioNavWindowPreset,
  markets: MarketCode[] = PERFORMANCE_MARKETS,
): Partial<Record<MarketCode, MarketSeriesPoint[]>> {
  if (preset === 'all') return rebasedByMarket;

  const endDate = latestSeriesEndDate(rebasedByMarket, markets);
  if (!endDate) return {};

  const startDate = resolveNavWindowStartDate(endDate, preset);
  const result: Partial<Record<MarketCode, MarketSeriesPoint[]>> = {};

  for (const market of markets) {
    const series = rebasedByMarket[market];
    if (!series?.length) continue;
    const marketEnd = series[series.length - 1].date;
    const sliced = sliceMarketWindow(series, startDate, marketEnd <= endDate ? marketEnd : endDate);
    const rebased = rebaseMarketSeries(sliced);
    if (rebased.length >= 2) {
      result[market] = rebased;
    }
  }

  return result;
}

export function pickWindowMasterSeries(
  windowRebasedByMarket: Partial<Record<MarketCode, MarketSeriesPoint[]>>,
  markets: MarketCode[] = PERFORMANCE_MARKETS,
) {
  return pickMasterMarketSeries(windowRebasedByMarket, markets);
}
