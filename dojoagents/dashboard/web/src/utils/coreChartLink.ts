import { formatKlineDate } from './klineDate';

/** Find the index whose date is closest to ``targetDate`` (YYYY-MM-DD). */
export function findClosestDateIndex(dates: string[], targetDate: string): number {
  if (!targetDate || dates.length === 0) return -1;

  const exact = dates.findIndex((date) => date === targetDate);
  if (exact >= 0) return exact;

  const targetMs = Date.parse(`${targetDate.slice(0, 10)}T12:00:00Z`);
  if (Number.isNaN(targetMs)) return dates.length - 1;

  let best = 0;
  let bestDiff = Infinity;
  for (let i = 0; i < dates.length; i += 1) {
    const ms = Date.parse(`${dates[i].slice(0, 10)}T12:00:00Z`);
    if (Number.isNaN(ms)) continue;
    const diff = Math.abs(ms - targetMs);
    if (diff < bestDiff) {
      bestDiff = diff;
      best = i;
    }
  }
  return best;
}

export function normalizeChartDates(items: Array<{ date: string }>): string[] {
  return items.map((item) => formatKlineDate(item.date));
}

/** Map a linked calendar date to an index within a visible slice, or null if off-screen. */
export function findVisibleIndexForLinkedDate(
  visibleItems: Array<{ date: string }>,
  linkedDate: string,
  visibleStartIndex: number,
  allItems: Array<{ date: string }>,
): number | null {
  const allDates = normalizeChartDates(allItems);
  const globalIndex = findClosestDateIndex(allDates, linkedDate);
  if (globalIndex < 0) return null;
  const visibleIndex = globalIndex - visibleStartIndex;
  if (visibleIndex < 0 || visibleIndex >= visibleItems.length) return null;
  return visibleIndex;
}
