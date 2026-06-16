import type { MarketCode } from '../types/dojoMesh';
import type { SectorPerformanceMarketPoint, SectorPerformancePoint } from '../types/dojoSphere';

export type PerformanceChartPoint = SectorPerformancePoint;

export const PERFORMANCE_MARKETS: MarketCode[] = ['us', 'sh', 'hk'];

export const PERFORMANCE_MARKET_CLASS: Record<MarketCode, string> = {
  us: 'us',
  sh: 'cn',
  hk: 'hk',
};

export interface MarketSeriesPoint {
  date: string;
  value: number;
}

export interface MarketPerformanceChip {
  market: MarketCode;
  date: string;
  value: number;
}

export interface PerformanceHeadSnapshot {
  /** Shared anchor when hovering a calendar date on the chart. */
  anchorDate?: string;
  markets: MarketPerformanceChip[];
}

export function forwardFillPerformanceSeries(
  points: PerformanceChartPoint[],
  markets: MarketCode[],
): PerformanceChartPoint[] {
  const last: Partial<Record<MarketCode, number>> = {};
  return points.map((point) => {
    const row: PerformanceChartPoint = { date: point.date };
    for (const market of markets) {
      const value = point[market];
      if (value != null && !Number.isNaN(value)) {
        last[market] = value;
      }
      if (last[market] != null) {
        row[market] = last[market];
      }
    }
    return row;
  });
}

export function rebasePerformanceSeries(
  points: SectorPerformancePoint[],
  markets: MarketCode[],
): PerformanceChartPoint[] {
  if (points.length === 0) return [];

  const baseValues: Partial<Record<MarketCode, number>> = {};
  for (const market of markets) {
    for (const point of points) {
      const value = point[market];
      if (value != null && value > 0) {
        baseValues[market] = value;
        break;
      }
    }
  }

  return points.map((point) => {
    const row: PerformanceChartPoint = { date: point.date };
    for (const market of markets) {
      const base = baseValues[market];
      const value = point[market];
      if (base != null && value != null && base > 0) {
        row[market] = Number(((value / base) * 100).toFixed(2));
      }
    }
    return row;
  });
}

export function rebaseMarketSeries(points: MarketSeriesPoint[]): MarketSeriesPoint[] {
  if (points.length === 0) return [];
  const base = points[0].value;
  if (base <= 0) return [];
  return points.map((point) => ({
    date: point.date,
    value: Number(((point.value / base) * 100).toFixed(2)),
  }));
}

export function toMarketSeriesPoints(
  points: SectorPerformanceMarketPoint[] | undefined,
): MarketSeriesPoint[] {
  if (!points?.length) return [];
  return points.map((point) => ({ date: point.date, value: point.value }));
}

export function buildIndependentMarketPath(
  points: MarketSeriesPoint[],
  width: number,
  height: number,
  yMin: number,
  yMax: number,
  padX = 6,
  padY = 6,
): string {
  if (points.length < 2) return '';

  const span = yMax - yMin || 1;
  const plotW = width - padX * 2;
  const plotH = height - padY * 2;
  let path = '';

  points.forEach((point, index) => {
    const x = padX + (index / (points.length - 1)) * plotW;
    const y = padY + plotH - ((point.value - yMin) / span) * plotH;
    path += `${index === 0 ? 'M' : 'L'}${x.toFixed(2)},${y.toFixed(2)}`;
  });

  return path;
}

export function lookupMarketValueOnOrBefore(
  points: MarketSeriesPoint[],
  date: string,
): MarketSeriesPoint | null {
  let last: MarketSeriesPoint | null = null;
  for (const point of points) {
    if (point.date <= date) {
      last = point;
    } else {
      break;
    }
  }
  return last;
}

export function findVisibleIndexForDate(
  points: MarketSeriesPoint[],
  date: string,
): number | null {
  if (!points.length || !date) return null;

  const exact = points.findIndex((point) => point.date === date);
  if (exact >= 0) return exact;

  let lastIndex = -1;
  for (let index = 0; index < points.length; index += 1) {
    if (points[index].date <= date) {
      lastIndex = index;
    } else {
      break;
    }
  }
  return lastIndex >= 0 ? lastIndex : null;
}

export function buildHoverSnapshotForDate(
  date: string,
  rebasedByMarket: Partial<Record<MarketCode, MarketSeriesPoint[]>>,
  markets: MarketCode[] = PERFORMANCE_MARKETS,
): { date: string; values: Partial<Record<MarketCode, number>> } | null {
  if (!date) return null;

  const values: Partial<Record<MarketCode, number>> = {};
  for (const market of markets) {
    const series = rebasedByMarket[market];
    if (!series?.length) continue;
    const hit = lookupMarketValueOnOrBefore(series, date);
    if (hit) values[market] = hit.value;
  }

  if (Object.keys(values).length === 0) return null;
  return { date, values };
}

function pseudoIndexFromReturnRatio(fromValue: number, toValue: number): number | null {
  if (fromValue <= 0) return null;
  const returnPct = (toValue / fromValue - 1) * 100;
  return Number((100 + returnPct).toFixed(2));
}

/** Return from anchor date through the latest point in each market series. */
export function buildReturnSinceDateSnapshot(
  fromDate: string,
  rebasedByMarket: Partial<Record<MarketCode, MarketSeriesPoint[]>>,
  markets: MarketCode[] = PERFORMANCE_MARKETS,
): PerformanceHeadSnapshot | null {
  if (!fromDate) return null;

  const chips: MarketPerformanceChip[] = [];
  for (const market of markets) {
    const series = rebasedByMarket[market];
    if (!series?.length) continue;
    const fromHit = lookupMarketValueOnOrBefore(series, fromDate);
    const latest = series[series.length - 1];
    if (!fromHit || !latest || fromHit.value <= 0) continue;
    const pseudo = pseudoIndexFromReturnRatio(fromHit.value, latest.value);
    if (pseudo != null) {
      chips.push({ market, date: latest.date, value: pseudo });
    }
  }

  if (chips.length === 0) return null;
  return { anchorDate: fromDate, markets: chips };
}

/** One-day return ending on the given calendar date (vs previous point in each series). */
export function buildOneDayReturnSnapshotForDate(
  date: string,
  rebasedByMarket: Partial<Record<MarketCode, MarketSeriesPoint[]>>,
  markets: MarketCode[] = PERFORMANCE_MARKETS,
): PerformanceHeadSnapshot | null {
  if (!date) return null;

  const chips: MarketPerformanceChip[] = [];
  for (const market of markets) {
    const series = rebasedByMarket[market];
    if (!series?.length) continue;
    const hitIndex = findVisibleIndexForDate(series, date);
    if (hitIndex == null || hitIndex < 1) continue;
    const prev = series[hitIndex - 1];
    const hit = series[hitIndex];
    const pseudo = pseudoIndexFromReturnRatio(prev.value, hit.value);
    if (pseudo != null) {
      chips.push({ market, date: hit.date, value: pseudo });
    }
  }

  if (chips.length === 0) return null;
  return { anchorDate: date, markets: chips };
}

/** One-day return between the last two points in each market series. */
export function buildLatestOneDayReturnSnapshot(
  rebasedByMarket: Partial<Record<MarketCode, MarketSeriesPoint[]>>,
  markets: MarketCode[] = PERFORMANCE_MARKETS,
): PerformanceHeadSnapshot | null {
  const chips: MarketPerformanceChip[] = [];

  for (const market of markets) {
    const series = rebasedByMarket[market];
    if (!series || series.length < 2) continue;
    const prev = series[series.length - 2];
    const last = series[series.length - 1];
    const pseudo = pseudoIndexFromReturnRatio(prev.value, last.value);
    if (pseudo != null) {
      chips.push({ market, date: last.date, value: pseudo });
    }
  }

  if (chips.length === 0) return null;
  return { markets: chips };
}

export function pickMasterMarketSeries(
  byMarket: Partial<Record<MarketCode, MarketSeriesPoint[]>>,
  markets: MarketCode[] = PERFORMANCE_MARKETS,
): { market: MarketCode; series: MarketSeriesPoint[] } | null {
  let best: { market: MarketCode; series: MarketSeriesPoint[] } | null = null;
  for (const market of markets) {
    const series = byMarket[market];
    if (!series?.length) continue;
    if (!best || series.length > best.series.length) {
      best = { market, series };
    }
  }
  return best;
}

export function formatPerformanceReturnPercent(indexValue: number): string {
  const pct = indexValue - 100;
  const sign = pct >= 0 ? '+' : '';
  return `${sign}${pct.toFixed(2)}%`;
}

/** Compact as-of label for sparkline chips (MM-DD). */
export function formatPerformanceAsOfDate(date: string): string {
  if (!date) return '';
  return date.length >= 10 ? date.slice(5) : date;
}

export function latestMarketDates(
  rebasedByMarket: Partial<Record<MarketCode, MarketSeriesPoint[]>>,
  markets: MarketCode[] = PERFORMANCE_MARKETS,
): Partial<Record<MarketCode, string>> {
  const result: Partial<Record<MarketCode, string>> = {};
  for (const market of markets) {
    const series = rebasedByMarket[market];
    if (series?.length) {
      result[market] = series[series.length - 1].date;
    }
  }
  return result;
}

export function buildMixedAxisEndLabel(
  endDates: Partial<Record<MarketCode, string>>,
  markets: MarketCode[] = PERFORMANCE_MARKETS,
): string {
  const entries = markets
    .map((market) => {
      const date = endDates[market];
      return date ? { market, date } : null;
    })
    .filter((entry): entry is { market: MarketCode; date: string } => entry != null);

  if (entries.length === 0) return '';
  const uniqueDates = new Set(entries.map((entry) => entry.date));
  if (uniqueDates.size <= 1) return entries[0].date;

  return entries
    .map(({ market, date }) => `${market.toUpperCase()} ${formatPerformanceAsOfDate(date)}`)
    .join(' · ');
}

export function sliceMarketSeriesByDateRange(
  points: MarketSeriesPoint[],
  startDate: string,
  endDate: string,
): MarketSeriesPoint[] {
  if (!points.length) return [];
  return points.filter((point) => point.date >= startDate && point.date <= endDate);
}

export function indexToChartX(
  index: number,
  count: number,
  width: number,
  padX: number,
): number {
  const plotW = width - padX * 2;
  if (count <= 1) return padX + plotW / 2;
  return padX + (index / (count - 1)) * plotW;
}

export function valueToChartY(
  value: number,
  yMin: number,
  yMax: number,
  height: number,
  padY: number,
): number {
  const span = yMax - yMin || 1;
  const plotH = height - padY * 2;
  return padY + plotH - ((value - yMin) / span) * plotH;
}

export function clampViewRange(
  start: number,
  end: number,
  minSpan: number,
): { start: number; end: number } {
  let nextStart = start;
  let nextEnd = end;
  const span = nextEnd - nextStart;

  if (span < minSpan) {
    const mid = (nextStart + nextEnd) / 2;
    nextStart = mid - minSpan / 2;
    nextEnd = mid + minSpan / 2;
  }

  if (nextStart < 0) {
    nextEnd -= nextStart;
    nextStart = 0;
  }
  if (nextEnd > 1) {
    nextStart -= nextEnd - 1;
    nextEnd = 1;
  }

  nextStart = Math.max(0, nextStart);
  nextEnd = Math.min(1, nextEnd);

  if (nextEnd - nextStart < minSpan) {
    if (nextStart <= 0) {
      nextEnd = Math.min(1, minSpan);
      nextStart = 0;
    } else {
      nextStart = Math.max(0, nextEnd - minSpan);
    }
  }

  return { start: nextStart, end: nextEnd };
}

/** @deprecated merged-calendar path builder; prefer buildIndependentMarketPath */
export function buildPerformancePath(
  values: Array<number | null | undefined>,
  width: number,
  height: number,
  min: number,
  max: number,
  offsetY = 0,
): string {
  const span = max - min || 1;
  let path = '';

  values.forEach((value, index) => {
    if (value == null || Number.isNaN(value)) {
      return;
    }
    const x = (index / Math.max(values.length - 1, 1)) * width;
    const y = offsetY + height - ((value - min) / span) * height;
    path += `${index === 0 || path === '' ? 'M' : 'L'}${x.toFixed(2)},${y.toFixed(2)}`;
  });

  return path;
}
