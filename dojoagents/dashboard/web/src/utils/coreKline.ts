import type { CoreTickerQuoteResponse } from '../api/dojoCore';
import type { CoreKlineBar, CoreKlineInterval } from '../types/dojoCore';
import type { CoreTickerKlineBar } from '../api/dojoCore';
import type { MarketCode } from '../types/dojoMesh';
import { formatKlineDate, KLINE_WINDOW_DAYS, subtractCalendarDays } from './klineDate';

const MARKET_IANA: Record<MarketCode, string> = {
  sh: 'Asia/Shanghai',
  hk: 'Asia/Shanghai',
  us: 'America/New_York',
};

const MARKET_REGULAR_OPEN: Record<MarketCode, [number, number]> = {
  sh: [9, 30],
  hk: [9, 30],
  us: [9, 30],
};

const PRE_CLOSE_MATCH_TOLERANCE = 0.002;

export const KLINE_INTERVAL_API: Record<CoreKlineInterval, string> = {
  '5m': '5m',
  '1D': '1D',
  '1W': '1W',
  '1M': '1M',
};

export const KLINE_INTERVAL_LIMIT: Record<CoreKlineInterval, number> = {
  '5m': 120,
  '1D': 270,
  '1W': 120,
  '1M': 60,
};

export const KLINE_DISPLAY_LIMIT: Record<CoreKlineInterval, number> = {
  '5m': 96,
  '1D': 0,
  '1W': 80,
  '1M': 48,
};

function normalizeBarDate(barTime: string): string {
  const text = barTime.trim();
  if (!text) return '';
  if (text.includes('T')) return text.split('T', 1)[0] ?? text;
  if (text.includes(' ')) return text.split(' ', 1)[0] ?? text;
  return text.slice(0, 10);
}

export function mapKlineBarToCore(bar: CoreTickerKlineBar): CoreKlineBar {
  return {
    date: normalizeBarDate(bar.bar_time),
    open: bar.open,
    high: bar.high,
    low: bar.low,
    close: bar.close,
    volume: bar.vol ?? 0,
    amount: bar.amount ?? 0,
  };
}

export function resolveCoreDailyChartWindow(
  market: MarketCode,
  now = new Date(),
): { start: string; end: string } {
  const end = marketLocalDateString(market, now);
  return {
    start: subtractCalendarDays(end, KLINE_WINDOW_DAYS),
    end,
  };
}

export function sliceCoreBarsToDateWindow(
  bars: CoreKlineBar[],
  window: { start: string; end: string },
): CoreKlineBar[] {
  if (!window.start || !window.end) return bars;
  return bars.filter((bar) => {
    const date = formatKlineDate(bar.date);
    return date >= window.start && date <= window.end;
  });
}

export function sliceCoreKlineToYearWindow(bars: CoreKlineBar[]): CoreKlineBar[] {
  if (!bars.length) return bars;
  const end = formatKlineDate(bars[bars.length - 1]!.date);
  if (!end) return bars;
  return sliceCoreBarsToDateWindow(bars, {
    start: subtractCalendarDays(end, KLINE_WINDOW_DAYS),
    end,
  });
}

export function mapKlineBarsToCore(
  bars: CoreTickerKlineBar[],
  interval: CoreKlineInterval,
): CoreKlineBar[] {
  const mapped = bars.map(mapKlineBarToCore);
  const limit = KLINE_DISPLAY_LIMIT[interval];
  return limit > 0 && mapped.length > limit ? mapped.slice(-limit) : mapped;
}

function preCloseMatchesKline(preClose: number, klineClose: number): boolean {
  if (preClose <= 0 || klineClose <= 0) return false;
  return Math.abs(preClose - klineClose) / klineClose <= PRE_CLOSE_MATCH_TOLERANCE;
}

export function marketLocalDateString(market: MarketCode, now = new Date()): string {
  const iana = MARKET_IANA[market] ?? 'UTC';
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: iana,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(now);
}

function marketLocalMinutes(market: MarketCode, now = new Date()): number {
  const iana = MARKET_IANA[market] ?? 'UTC';
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: iana,
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).formatToParts(now);
  const hour = Number(parts.find((part) => part.type === 'hour')?.value ?? 0);
  const minute = Number(parts.find((part) => part.type === 'minute')?.value ?? 0);
  return hour * 60 + minute;
}

export function marketRegularSessionHasStarted(market: MarketCode, now = new Date()): boolean {
  const [openHour, openMinute] = MARKET_REGULAR_OPEN[market] ?? [9, 30];
  return marketLocalMinutes(market, now) >= openHour * 60 + openMinute;
}

export function quoteSessionLeadsKline(
  quote: CoreTickerQuoteResponse,
  bars: CoreKlineBar[],
  market: MarketCode,
  now = new Date(),
): boolean {
  if (!bars.length) return false;
  if (!marketRegularSessionHasStarted(market, now)) return false;
  const sessionDate = marketLocalDateString(market, now);
  const lastBar = bars[bars.length - 1]!;
  const lastDate = normalizeBarDate(lastBar.date);
  if (sessionDate <= lastDate) return false;
  return preCloseMatchesKline(quote.pre_close, lastBar.close);
}

function buildQuoteSessionBar(quote: CoreTickerQuoteResponse, sessionDate: string): CoreKlineBar {
  return {
    date: sessionDate,
    open: quote.open,
    high: quote.high,
    low: quote.low,
    close: quote.last_price,
    volume: quote.volume,
    amount: quote.amount ?? 0,
  };
}

/** Append or refresh today's bar from live quote when daily kline lags the session. */
export function mergeQuoteIntoDailyKline(
  bars: CoreKlineBar[],
  quote: CoreTickerQuoteResponse | null | undefined,
  market: MarketCode | null | undefined,
  now = new Date(),
): CoreKlineBar[] {
  if (!quote || !market || !bars.length) return bars;
  if (!quoteSessionLeadsKline(quote, bars, market, now)) return bars;

  const sessionDate = marketLocalDateString(market, now);
  const quoteBar = buildQuoteSessionBar(quote, sessionDate);
  const lastDate = normalizeBarDate(bars[bars.length - 1]!.date);
  if (lastDate === sessionDate) {
    return [...bars.slice(0, -1), quoteBar];
  }
  return [...bars, quoteBar];
}
