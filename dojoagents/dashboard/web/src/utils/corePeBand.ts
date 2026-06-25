import type { CorePeBandPoint } from '../types/dojoCore';
import { formatKlineDate } from './klineDate';

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
