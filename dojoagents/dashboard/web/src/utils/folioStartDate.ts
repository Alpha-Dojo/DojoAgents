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

/** Earliest selectable start date: min(1 year ago, first performance data point). */
export function computeStartDateBounds(earliestDataDate?: string | null): { min: string; max: string } {
  const max = todayIsoDate();
  const rollingMin = oneYearAgoDate();
  if (!earliestDataDate || earliestDataDate >= rollingMin) {
    return { min: rollingMin, max };
  }
  return { min: earliestDataDate, max };
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
