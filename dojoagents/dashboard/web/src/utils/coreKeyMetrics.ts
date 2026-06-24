import type { CoreTickerQuoteResponse } from '../api/dojoCore';
import type { MarketCode } from '../types/dojoMesh';
import type { CoreKeyMetric, CoreKlineBar, CorePeBandPoint, StockFinIndicatorRow } from '../types/dojoCore';
import { extractReportDate, resolveHkPeriodFinRow } from './coreFinIndicators';
import { resolvePeBandPeForDate } from './corePeBand';
import { formatMarketCap, formatPe, formatStockPrice } from './marketStats';

const METRIC_ROWS: CoreKeyMetric['labelKey'][][] = [
  [
    'marketCap',
    'totalShares',
    'peTtm',
    'peDynamic',
    'pbRatio',
    'epsBasic',
    'roe',
  ],
  [
    'roa',
    'grossMargin',
    'netMargin',
    'dividendYield',
    'turnover',
    'week52Range',
  ],
];

export const CORE_METRIC_COLUMN_COUNT = Math.max(...METRIC_ROWS.map((row) => row.length));

function isValidNumber(value: number | null | undefined): value is number {
  return value != null && Number.isFinite(value) && value > 0;
}

function isValidSignedNumber(value: number | null | undefined): value is number {
  return value != null && Number.isFinite(value);
}

function latestFinRow(rows: StockFinIndicatorRow[]): StockFinIndicatorRow | null {
  if (!rows.length) return null;
  return [...rows].sort((a, b) => extractReportDate(a).localeCompare(extractReportDate(b))).at(-1) ?? null;
}

function formatPercent(value: number, digits = 2): string {
  return `${value.toFixed(digits)}%`;
}

function formatPeDisplay(value: number | null, lossLabel?: string): string {
  if (value == null || !Number.isFinite(value) || value === 0) return '—';
  if (value < 0) return lossLabel ?? '—';
  return value.toFixed(1);
}

function resolveCurrency(currency?: string | null): string | undefined {
  const code = currency?.trim();
  return code || undefined;
}

function resolveWeek52Range(bars: CoreKlineBar[]): { high: number; low: number } | null {
  if (!bars.length) return null;
  let high = Number.NEGATIVE_INFINITY;
  let low = Number.POSITIVE_INFINITY;
  for (const bar of bars) {
    if (!Number.isFinite(bar.high) || !Number.isFinite(bar.low)) continue;
    high = Math.max(high, bar.high);
    low = Math.min(low, bar.low);
  }
  if (!Number.isFinite(high) || !Number.isFinite(low) || high <= 0 || low <= 0) return null;
  return { high, low };
}

function resolveTurnoverRate(volume: number | null, totalShares: number | null): number | null {
  if (volume == null || !isValidNumber(totalShares)) return null;
  return (volume / totalShares) * 100;
}

export function buildCoreKeyMetrics(input: {
  quote: CoreTickerQuoteResponse | null;
  finRows: StockFinIndicatorRow[];
  klineBars: CoreKlineBar[];
  peBandPoints?: CorePeBandPoint[];
  chartAnchorDate?: string | null;
  market?: MarketCode | null;
  currency?: string | null;
  peLossLabel?: string;
}): CoreKeyMetric[][] {
  const currency = resolveCurrency(input.currency ?? input.quote?.currency);
  const latestRawFin = latestFinRow(input.finRows);
  const periodFin = resolveHkPeriodFinRow(input.finRows, input.market);

  const marketCap = isValidNumber(input.quote?.market_cap) ? input.quote.market_cap : null;
  const totalShares = isValidNumber(input.quote?.total_shares) ? input.quote.total_shares : null;
  const peDynamic = isValidSignedNumber(input.quote?.pe) ? input.quote.pe : null;
  const peTtm = resolvePeBandPeForDate(input.peBandPoints ?? [], input.chartAnchorDate);
  const pb = isValidSignedNumber(input.quote?.pb) ? input.quote.pb : null;
  const epsBasic = isValidSignedNumber(periodFin?.eps_basic) ? periodFin.eps_basic : null;
  const roe = isValidSignedNumber(periodFin?.roe_weighted) ? periodFin.roe_weighted : null;
  const roa = isValidSignedNumber(periodFin?.roa) ? periodFin.roa : null;
  const grossMargin = isValidSignedNumber(latestRawFin?.gross_margin) ? latestRawFin.gross_margin : null;
  const netMargin = isValidSignedNumber(latestRawFin?.net_margin) ? latestRawFin.net_margin : null;
  const dividendYield = isValidNumber(latestRawFin?.dividend_rate) ? latestRawFin.dividend_rate : null;
  const week52 = resolveWeek52Range(input.klineBars);
  const volume =
    input.quote?.volume != null && Number.isFinite(input.quote.volume) && input.quote.volume > 0
      ? input.quote.volume
      : null;
  const turnover = resolveTurnoverRate(volume, totalShares);

  const byKey: Record<string, CoreKeyMetric> = {
    marketCap: {
      labelKey: 'marketCap',
      value: marketCap != null ? formatMarketCap(marketCap) : '—',
      subValue: currency,
    },
    totalShares: {
      labelKey: 'totalShares',
      value: totalShares != null ? formatMarketCap(totalShares) : '—',
    },
    peTtm: {
      labelKey: 'peTtm',
      value: formatPeDisplay(peTtm, input.peLossLabel),
    },
    peDynamic: {
      labelKey: 'peDynamic',
      value: formatPeDisplay(peDynamic, input.peLossLabel),
    },
    pbRatio: {
      labelKey: 'pbRatio',
      value: pb != null ? formatPe(pb) : '—',
    },
    epsBasic: {
      labelKey: 'epsBasic',
      value: epsBasic != null ? formatStockPrice(epsBasic) : '—',
      subValue: currency,
    },
    roe: {
      labelKey: 'roe',
      value: roe != null ? formatPercent(roe) : '—',
    },
    roa: {
      labelKey: 'roa',
      value: roa != null ? formatPercent(roa) : '—',
    },
    grossMargin: {
      labelKey: 'grossMargin',
      value: grossMargin != null ? formatPercent(grossMargin) : '—',
    },
    netMargin: {
      labelKey: 'netMargin',
      value: netMargin != null ? formatPercent(netMargin) : '—',
    },
    dividendYield: {
      labelKey: 'dividendYield',
      value: dividendYield != null ? formatPercent(dividendYield) : '—',
    },
    turnover: {
      labelKey: 'turnover',
      value: turnover != null ? formatPercent(turnover) : '—',
    },
    week52Range: {
      labelKey: 'week52Range',
      value: week52
        ? `${formatStockPrice(week52.high)} / ${formatStockPrice(week52.low)}`
        : '—',
    },
  };

  return METRIC_ROWS.map((rowKeys) => rowKeys.map((labelKey) => byKey[labelKey]!));
}
