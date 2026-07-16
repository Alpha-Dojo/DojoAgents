/** Calendar-day helpers for market dynamics windows (YYYY-MM-DD). */

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

export function toCalendarDate(value: string | null | undefined): string {
  const raw = String(value || '').trim();
  if (!raw) return '';
  const day = raw.slice(0, 10);
  return DATE_RE.test(day) ? day : '';
}

export function addCalendarDays(date: string, delta: number): string {
  const day = toCalendarDate(date);
  if (!day) return '';
  const [y, m, d] = day.split('-').map(Number);
  const next = new Date(Date.UTC(y, m - 1, d));
  next.setUTCDate(next.getUTCDate() + delta);
  return next.toISOString().slice(0, 10);
}

export function windowBounds(centerDate: string, radiusDays: number): {
  startDate: string;
  endDate: string;
} {
  const center = toCalendarDate(centerDate);
  return {
    startDate: addCalendarDays(center, -radiusDays),
    endDate: addCalendarDays(center, radiusDays),
  };
}

export function mergeSortedEventsById<T extends { id: string; event_time: string; trading_date?: string }>(
  existing: T[],
  incoming: T[],
): T[] {
  if (incoming.length === 0) return existing;
  if (existing.length === 0) return incoming;
  const map = new Map<string, T>();
  for (const event of existing) map.set(event.id, event);
  for (const event of incoming) map.set(event.id, event);
  return [...map.values()].sort((a, b) => {
    const da = (a.trading_date || a.event_time || '').slice(0, 10);
    const db = (b.trading_date || b.event_time || '').slice(0, 10);
    if (da !== db) return da < db ? -1 : 1;
    if (a.event_time !== b.event_time) return a.event_time < b.event_time ? -1 : 1;
    return a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
  });
}
