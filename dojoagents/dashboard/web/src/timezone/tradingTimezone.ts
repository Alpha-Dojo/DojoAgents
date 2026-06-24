export type TradingTimezoneId = 'bjt' | 'hkt' | 'utc' | 'et';

export interface TradingTimezone {
  id: TradingTimezoneId;
  iana: string;
  label: string;
}

export const TRADING_TIMEZONES: TradingTimezone[] = [
  { id: 'bjt', iana: 'Asia/Shanghai', label: 'BJT' },
  { id: 'hkt', iana: 'Asia/Hong_Kong', label: 'HKT' },
  { id: 'utc', iana: 'UTC', label: 'UTC' },
  { id: 'et', iana: 'America/New_York', label: 'ET' },
];

const STORAGE_KEY = 'alphadojo-trading-timezone';

export function isTradingTimezoneId(value: unknown): value is TradingTimezoneId {
  return value === 'bjt' || value === 'hkt' || value === 'utc' || value === 'et';
}

export function readStoredTradingTimezone(): TradingTimezoneId {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return isTradingTimezoneId(raw) ? raw : 'bjt';
  } catch {
    return 'bjt';
  }
}

export function storeTradingTimezone(id: TradingTimezoneId) {
  try {
    localStorage.setItem(STORAGE_KEY, id);
  } catch {
    /* ignore */
  }
}

export function getTradingTimezone(id: TradingTimezoneId): TradingTimezone {
  return TRADING_TIMEZONES.find((tz) => tz.id === id) ?? TRADING_TIMEZONES[0];
}

const clockFormatterCache = new Map<string, Intl.DateTimeFormat>();

function getClockFormatter(iana: string): Intl.DateTimeFormat {
  let formatter = clockFormatterCache.get(iana);
  if (!formatter) {
    formatter = new Intl.DateTimeFormat('en-GB', {
      timeZone: iana,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });
    clockFormatterCache.set(iana, formatter);
  }
  return formatter;
}

export function formatTradingClock(now: Date, timezoneId: TradingTimezoneId): string {
  const { iana } = getTradingTimezone(timezoneId);
  return getClockFormatter(iana).format(now);
}
