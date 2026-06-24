/** Normalize kline datetime to YYYY-MM-DD for display. */
export function formatKlineDate(datetime: string | number | undefined | null): string {
  if (datetime == null) return '';
  const raw = String(datetime).trim();
  if (!raw) return '';

  if (/^\d{4}-\d{2}-\d{2}/.test(raw)) {
    return raw.slice(0, 10);
  }

  if (/^\d{8}$/.test(raw)) {
    return `${raw.slice(0, 4)}-${raw.slice(4, 6)}-${raw.slice(6, 8)}`;
  }

  const num = Number(raw);
  if (!Number.isNaN(num) && num > 0) {
    const ms = num > 1e12 ? num : num * 1000;
    const date = new Date(ms);
    if (!Number.isNaN(date.getTime())) {
      return date.toISOString().slice(0, 10);
    }
  }

  return raw.slice(0, 10) || raw;
}

export function formatKlineAxisDate(datetime: string, showYear: boolean): string {
  const date = formatKlineDate(datetime);
  if (date.length !== 10) return date;
  return showYear ? date : date.slice(5);
}

/** Resolve display date for a bar; interpolates when datetime is missing. */
export function resolveKlineBarDate(kline: { datetime: string }[], index: number): string {
  const direct = formatKlineDate(kline[index]?.datetime);
  if (direct) return direct;

  let left = index;
  while (left >= 0 && !formatKlineDate(kline[left]?.datetime)) left -= 1;
  let right = index;
  while (right < kline.length && !formatKlineDate(kline[right]?.datetime)) right += 1;

  const leftDate = left >= 0 ? formatKlineDate(kline[left].datetime) : '';
  const rightDate = right < kline.length ? formatKlineDate(kline[right].datetime) : '';

  if (leftDate && rightDate && left !== right) {
    const start = Date.parse(`${leftDate}T12:00:00Z`);
    const end = Date.parse(`${rightDate}T12:00:00Z`);
    if (!Number.isNaN(start) && !Number.isNaN(end)) {
      const ratio = (index - left) / (right - left);
      return new Date(start + (end - start) * ratio).toISOString().slice(0, 10);
    }
  }

  return leftDate || rightDate;
}

/** Find the kline bar index closest to a calendar date (YYYY-MM-DD). */
export function findKlineIndexForDate(
  kline: { datetime: string }[],
  targetDate: string,
): number {
  if (!targetDate || kline.length === 0) return Math.max(0, kline.length - 1);

  const dates = kline.map((_, i) => resolveKlineBarDate(kline, i));
  const exact = dates.indexOf(targetDate);
  if (exact >= 0) return exact;

  const targetMs = Date.parse(`${targetDate}T12:00:00Z`);
  if (Number.isNaN(targetMs)) return kline.length - 1;

  let best = 0;
  let bestDiff = Infinity;
  for (let i = 0; i < dates.length; i += 1) {
    const ms = Date.parse(`${dates[i]}T12:00:00Z`);
    if (Number.isNaN(ms)) continue;
    const diff = Math.abs(ms - targetMs);
    if (diff < bestDiff) {
      bestDiff = diff;
      best = i;
    }
  }
  return best;
}

export const DATA_START_DATE = '2025-01-01';

/** @deprecated Rolling 1Y window; charts now anchor at {@link DATA_START_DATE}. */
export const KLINE_WINDOW_DAYS = 365;

export function subtractCalendarDays(isoDate: string, days: number): string {
  const parsed = Date.parse(`${isoDate.slice(0, 10)}T12:00:00Z`);
  if (Number.isNaN(parsed)) return isoDate.slice(0, 10);
  const next = new Date(parsed);
  next.setUTCDate(next.getUTCDate() - days);
  return next.toISOString().slice(0, 10);
}

export function resolveLatestKlineDate(kline: { datetime: string }[]): string {
  let latest = '';
  for (const bar of kline) {
    const date = formatKlineDate(bar.datetime);
    if (date > latest) latest = date;
  }
  return latest;
}

export function resolveKlineYearWindow(
  kline: { datetime: string }[],
): { start: string; end: string } | null {
  const end = resolveLatestKlineDate(kline);
  if (!end) return null;
  return {
    start: DATA_START_DATE,
    end,
  };
}

export type KlineYearWindow = { start: string; end: string };

/**
 * Per-market chart windows with a unified start at local data inception.
 */
export function resolveAlignedKlineYearWindowsByMarket(
  latestEndByMarket: Partial<Record<string, string>>,
): Partial<Record<string, KlineYearWindow>> {
  const ends = Object.values(latestEndByMarket).filter(Boolean) as string[];
  if (ends.length === 0) return {};

  const windows: Partial<Record<string, KlineYearWindow>> = {};
  for (const [market, end] of Object.entries(latestEndByMarket)) {
    if (!end) continue;
    windows[market] = { start: DATA_START_DATE, end };
  }
  return windows;
}

export function resolveAlignedKlineYearWindowsFromBars(
  barsByMarket: Partial<Record<string, { datetime: string }[]>>,
): Partial<Record<string, KlineYearWindow>> {
  const latestEndByMarket: Partial<Record<string, string>> = {};
  for (const [market, bars] of Object.entries(barsByMarket)) {
    if (!bars?.length) continue;
    const end = resolveLatestKlineDate(bars);
    if (end) latestEndByMarket[market] = end;
  }
  return resolveAlignedKlineYearWindowsByMarket(latestEndByMarket);
}

export function sliceKlineToWindow<T extends { datetime: string }>(
  kline: T[],
  windowStart: string,
  windowEnd: string,
): T[] {
  if (!windowStart || !windowEnd) return kline;
  return kline.filter((bar) => {
    const date = formatKlineDate(bar.datetime);
    return date >= windowStart && date <= windowEnd;
  });
}
