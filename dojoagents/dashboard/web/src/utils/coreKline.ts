import type { CoreKlineBar, CoreKlineInterval, CoreQuoteSnapshot } from '../types/dojoCore';
import type { CoreTickerKlineBar } from '../api/dojoCore';
import type { MarketCode } from '../types/dojoMesh';
import { DATA_START_DATE, formatKlineDate } from './klineDate';

const MARKET_IANA: Record<MarketCode, string> = {
  cn: 'Asia/Shanghai',
  hk: 'Asia/Shanghai',
  us: 'America/New_York',
};

const MARKET_CURRENCY: Record<MarketCode, string> = {
  cn: 'CNY',
  hk: 'HKD',
  us: 'USD',
};

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

export function marketLocalDateString(market: MarketCode, now = new Date()): string {
  const iana = MARKET_IANA[market] ?? 'UTC';
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: iana,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(now);
}

/** API fetch window; daily bars refresh after market close. */
export function resolveCoreDailyChartWindow(
  market: MarketCode,
  now = new Date(),
): { start: string; end: string } {
  return {
    start: DATA_START_DATE,
    end: marketLocalDateString(market, now),
  };
}

export function resolveLatestKlineAnchorDate(bars: CoreKlineBar[]): string | null {
  if (!bars.length) return null;
  const date = formatKlineDate(bars[bars.length - 1]!.date);
  return date || null;
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
    start: DATA_START_DATE,
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

/** Header price/change from the latest daily bar (no live quote). */
export function buildQuoteSnapshotFromKlineBars(
  bars: CoreKlineBar[],
  market?: MarketCode | null,
): CoreQuoteSnapshot | null {
  if (!bars.length) return null;

  const last = bars[bars.length - 1]!;
  if (!(last.close > 0)) return null;

  const prev = bars.length > 1 ? bars[bars.length - 2]! : null;
  const prevClose = prev && prev.close > 0 ? prev.close : last.open > 0 ? last.open : last.close;
  const change = last.close - prevClose;
  const changePercent = prevClose > 0 ? (change / prevClose) * 100 : 0;

  return {
    price: last.close,
    change,
    changePercent,
    currency: market ? MARKET_CURRENCY[market] ?? 'USD' : 'USD',
  };
}
