import { DATA_START_DATE, FOLIO_DEFAULT_START_DATE } from './klineDate';

function formatIsoDate(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export function oneYearAgoDate(from: Date = new Date()): string {
  const date = new Date(from);
  date.setFullYear(date.getFullYear() - 1);
  return formatIsoDate(date);
}

export function todayIsoDate(from: Date = new Date()): string {
  return formatIsoDate(from);
}

/** Default 建仓日：持仓最早建仓日，否则 2025 年 1 月首个交易日。 */
export function resolvePortfolioStartDate(detail: {
  positions?: Array<{ openDate?: string }>;
}): string {
  const openDates = (detail.positions ?? [])
    .map((row) => row.openDate?.slice(0, 10))
    .filter((value): value is string => Boolean(value));
  if (openDates.length > 0) {
    return openDates.sort()[0];
  }
  return FOLIO_DEFAULT_START_DATE;
}

export function portfolioDefaultConfig(
  detail: {
    positions?: Array<{ openDate?: string }>;
  },
  base: { startDate: string; costDate: string; capitalByMarket: Record<string, number> },
): { startDate: string; costDate: string; capitalByMarket: Record<string, number> } {
  const startDate = resolvePortfolioStartDate(detail);
  return {
    ...base,
    startDate,
    costDate: startDate,
  };
}

/** Earliest selectable date: global dataset inception (2025-01-01) through today. */
export function computeStartDateBounds(floorDate?: string | null): { min: string; max: string } {
  const max = todayIsoDate();
  const min = floorDate && floorDate > DATA_START_DATE ? floorDate : DATA_START_DATE;
  return { min, max };
}

export function enumerateIsoDates(min: string, max: string): string[] {
  const dates: string[] = [];
  const cursor = new Date(`${min}T12:00:00`);
  const end = new Date(`${max}T12:00:00`);
  while (cursor <= end) {
    dates.push(formatIsoDate(cursor));
    cursor.setDate(cursor.getDate() + 1);
  }
  return dates.reverse();
}

export function clampStartDate(value: string, min: string, max: string): string {
  if (value < min) return min;
  if (value > max) return max;
  return value;
}
