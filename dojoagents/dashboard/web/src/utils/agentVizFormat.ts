import { formatMarketCap } from './marketStats';
import { formatCompactAmount } from './folioFormat';

export function formatVizCompactAmount(value: unknown): string {
  const num = typeof value === 'number' ? value : Number(String(value ?? '').replace(/,/g, ''));
  if (!Number.isFinite(num)) return '—';
  return formatCompactAmount(num);
}

export function formatVizPercent(value: unknown): string {
  const num = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(num)) return '—';
  const sign = num > 0 ? '+' : '';
  return `${sign}${num.toFixed(2)}%`;
}

export function formatVizNumber(value: unknown, digits = 2): string {
  const num = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(num)) return '—';
  return num.toFixed(digits);
}

export function formatVizCell(value: unknown, format?: string): string {
  if (value == null || value === '') return '—';
  switch (format) {
    case 'percent':
      return formatVizPercent(value);
    case 'number':
      return formatVizNumber(value);
    case 'market_cap':
      return formatMarketCap(typeof value === 'number' ? value : Number(value));
    case 'currency_usd': {
      const num = typeof value === 'number' ? value : Number(value);
      if (!Number.isFinite(num)) return '—';
      return `$${formatMarketCap(num)}`;
    }
    case 'compact_amount':
      return formatVizCompactAmount(value);
    default:
      return String(value);
  }
}

export function percentTone(value: unknown): 'up' | 'down' | 'flat' {
  const num = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(num) || num === 0) return 'flat';
  return num > 0 ? 'up' : 'down';
}

export const AGENT_VIZ_SLICE_COLORS = [
  '#00e5ff',
  '#00e676',
  '#ff9800',
  '#5c6bc0',
  '#26c6da',
  '#ab47bc',
  '#78909c',
  '#ef5350',
] as const;

export const AGENT_VIZ_LINE_COLORS = ['#00e5ff', '#00e676', '#ff9800', '#ab47bc'] as const;
