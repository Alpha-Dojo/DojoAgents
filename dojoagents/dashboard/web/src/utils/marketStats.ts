import type { MarketCode } from '../types/dojoMesh';

/** Aggregate exchange statistics shown above each market column. */
export interface MarketStats {
  market: MarketCode;
  /** Total listed companies (non-delisted tickers in universe). */
  listed_count: number;
  /** Sum of market cap for quoted stocks. */
  total_market_cap: number;
  /** Aggregate PE: total market cap / sum(cap/pe), earnings-weighted, pe>0 only. */
  weighted_pe: number | null;
  /** Arithmetic mean PE, pe>0 only. */
  simple_pe: number | null;
  /** Stocks with valid positive PE in PE calculations. */
  pe_sample_count: number;
}

export const MARKET_CAP_LABEL: Record<MarketCode, string> = {
  us: '市值(美元)',
  cn: '市值(人民币)',
  hk: '市值(港元)',
};

export function formatMarketCap(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return '—';
  const abs = Math.abs(value);
  if (abs >= 1e12) return `${(value / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) {
    const b = value / 1e9;
    return b >= 100 ? `${Math.round(b)}B` : `${b.toFixed(1)}B`;
  }
  if (abs >= 1e6) return `${Math.round(value / 1e6)}M`;
  if (abs >= 1e3) return `${Math.round(value / 1e3)}K`;
  return String(Math.round(value));
}

export function formatMarketCapCard(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return '—';
  const abs = Math.abs(value);
  if (abs >= 1e12) {
    const t = value / 1e12;
    return `${t.toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}T`;
  }
  if (abs >= 1e9) {
    const b = value / 1e9;
    const text = b >= 100 ? Math.round(b).toLocaleString('en-US') : b.toFixed(1);
    return `${text}B`;
  }
  if (abs >= 1e6) return `${Math.round(value / 1e6).toLocaleString('en-US')}M`;
  return formatMarketCap(value);
}

export type FormatPeOptions = {
  /** When set, negative P/E is shown as this label instead of a numeric value. */
  lossLabel?: string;
};

export function formatPe(value: number | null, options?: FormatPeOptions): string {
  if (value == null || !Number.isFinite(value) || value === 0) return '—';
  if (value < 0) {
    return options?.lossLabel ?? value.toFixed(2);
  }
  return value.toFixed(2);
}

export function isNegativeValuationRatio(value: number | null | undefined): boolean {
  return value != null && Number.isFinite(value) && value < 0;
}

/** Rounded PE for compact card footer. */
export function formatPeShort(value: number | null): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return String(Math.round(value));
}

/** Short cap label for compact chart callouts. */
export function formatMarketCapChart(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return '—';
  const abs = Math.abs(value);
  if (abs >= 1e12) return `${(value / 1e12).toFixed(1)}T`;
  if (abs >= 1e9) {
    const b = value / 1e9;
    return b >= 100 ? `${Math.round(b)}B` : `${b.toFixed(0)}B`;
  }
  if (abs >= 1e6) return `${Math.round(value / 1e6)}M`;
  return formatMarketCap(value);
}

/** Rounded PE for compact chart callouts. */
export function formatPeChart(value: number | null): string {
  return formatPeShort(value);
}

/** Integer display without thousands separators. */
export function formatPlainCount(value: number): string {
  return String(Math.round(value));
}

export function formatStockPrice(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—';
  if (value >= 1000) return value.toFixed(2);
  if (value >= 1) return value.toFixed(2);
  return value.toFixed(4);
}

export function formatSignedPercent(value: number | null | undefined, digits = 2): string {
  if (value == null || !Number.isFinite(value)) return '—';
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toFixed(digits)}%`;
}

export function normalizePercent(value: number | null | undefined): number {
  if (value == null || !Number.isFinite(value)) return 0;
  return value;
}
