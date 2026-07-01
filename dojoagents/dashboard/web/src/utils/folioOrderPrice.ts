import { fetchCoreTickerKline } from '../api/entity';
import type { MarketCode } from '../types/market';
import { formatStockPrice } from './marketStats';

function normalizeBarDate(barTime: string): string {
  const text = barTime.trim();
  if (!text) return '';
  if (text.includes('T')) return text.split('T', 1)[0] ?? text;
  if (text.includes(' ')) return text.split(' ', 1)[0] ?? text;
  return text.slice(0, 10);
}

/** Opening price for a ticker on a given ISO date (YYYY-MM-DD). */
export async function fetchTickerOpenOnDate(
  ticker: string,
  market: MarketCode,
  date: string,
): Promise<number | null> {
  const response = await fetchCoreTickerKline({
    ticker,
    market,
    start_date: date,
    end_date: date,
    limit: 8,
  });

  const exact = response.bars.find((bar) => normalizeBarDate(bar.bar_time) === date && bar.open > 0);
  return exact?.open ?? null;
}

export function formatOrderLimitPrice(value: number): string {
  const formatted = formatStockPrice(value);
  return formatted === '—' ? '' : formatted;
}
