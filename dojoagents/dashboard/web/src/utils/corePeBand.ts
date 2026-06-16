import type { CoreTickerQuoteResponse } from '../api/dojoCore';
import type { CoreKlineBar, CorePeBandPoint } from '../types/dojoCore';
import type { MarketCode } from '../types/dojoMesh';
import { formatKlineDate } from './klineDate';
import { marketLocalDateString, quoteSessionLeadsKline } from './coreKline';

function round2(value: number): number {
  return Math.round(value * 100) / 100;
}

function normalizePointDate(date: string): string {
  return date.trim().slice(0, 10);
}

function findKlineCloseOnDate(bars: CoreKlineBar[], date: string): number | null {
  const target = normalizePointDate(date);
  for (let index = bars.length - 1; index >= 0; index -= 1) {
    const bar = bars[index]!;
    const barDate = normalizePointDate(bar.date);
    if (barDate === target) return bar.close;
    if (barDate < target) break;
  }
  return null;
}

function computeBandFields(
  allPes: number[],
): Pick<CorePeBandPoint, 'mean' | 'upper1' | 'lower1' | 'upper2' | 'lower2'> {
  if (!allPes.length) {
    return { mean: 0, upper1: 0, lower1: 0, upper2: 0, lower2: 0 };
  }
  const mean = allPes.reduce((sum, pe) => sum + pe, 0) / allPes.length;
  if (allPes.length === 1) {
    const rounded = round2(mean);
    return { mean: rounded, upper1: rounded, lower1: rounded, upper2: rounded, lower2: rounded };
  }
  const variance = allPes.reduce((sum, pe) => sum + (pe - mean) ** 2, 0) / allPes.length;
  const std = Math.sqrt(variance);
  return {
    mean: round2(mean),
    upper1: round2(mean + std),
    lower1: round2(mean - std),
    upper2: round2(mean + 2 * std),
    lower2: round2(mean - 2 * std),
  };
}

function applyBandStats(points: CorePeBandPoint[]): CorePeBandPoint[] {
  const bands = computeBandFields(points.map((point) => point.pe));
  return points.map((point) => ({ ...point, ...bands }));
}

/** Append or refresh today's PE from live quote when daily kline lags the session. */
export function mergeQuoteIntoPeBand(
  points: CorePeBandPoint[],
  klineBars: CoreKlineBar[],
  quote: CoreTickerQuoteResponse | null | undefined,
  market: MarketCode | null | undefined,
  now = new Date(),
): CorePeBandPoint[] {
  if (!quote || !market || !points.length || !klineBars.length) return points;
  if (!quoteSessionLeadsKline(quote, klineBars, market, now)) return points;

  const lastPe = points[points.length - 1]!;
  const refClose = findKlineCloseOnDate(klineBars, lastPe.date);
  if (refClose == null || refClose <= 0 || lastPe.pe <= 0 || quote.last_price <= 0) return points;

  const sessionPe = round2(lastPe.pe * (quote.last_price / refClose));
  if (!Number.isFinite(sessionPe) || sessionPe <= 0) return points;

  const sessionDate = marketLocalDateString(market, now);
  const lastPeDate = normalizePointDate(lastPe.date);
  let nextPoints: CorePeBandPoint[];

  if (lastPeDate === sessionDate) {
    nextPoints = [...points.slice(0, -1), { ...lastPe, date: sessionDate, pe: sessionPe }];
  } else {
    nextPoints = [
      ...points,
      {
        date: sessionDate,
        pe: sessionPe,
        mean: 0,
        upper1: 0,
        lower1: 0,
        upper2: 0,
        lower2: 0,
      },
    ];
  }

  return applyBandStats(nextPoints);
}

export function resolvePeBandPeForDate(
  points: CorePeBandPoint[],
  date: string | null | undefined,
): number | null {
  if (!points.length) return null;

  const target = date ? formatKlineDate(date) : '';
  if (target) {
    for (let index = points.length - 1; index >= 0; index -= 1) {
      const point = points[index]!;
      if (formatKlineDate(point.date) === target) {
        return Number.isFinite(point.pe) ? point.pe : null;
      }
    }
  }

  const latest = points[points.length - 1]!;
  return Number.isFinite(latest.pe) ? latest.pe : null;
}

export function slicePePointsToDateWindow(
  points: CorePeBandPoint[],
  window: { start: string; end: string },
): CorePeBandPoint[] {
  if (!window.start || !window.end) return points;
  return points.filter((point) => {
    const date = formatKlineDate(point.date);
    return date >= window.start && date <= window.end;
  });
}
