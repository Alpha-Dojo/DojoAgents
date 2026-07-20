import type { MarketCode } from '../types/market';
import type { EntityKeyMetric, EntityKlineBar, EntityPeBandPoint, StockFinIndicatorRow } from '../types/entity';
import type { CoreTickerQuoteResponse } from '../api/entity';
import { extractReportDate, resolveHkPeriodFinRow, resolveRollingTtmNetProfit } from './entityFinIndicators';
import { resolvePeBandPeForDate } from './entityPeBand';
import { formatMarketCap, formatPe, formatStockPrice } from './marketStats';

const MARKET_CURRENCY: Record<MarketCode, string> = {
  cn: 'CNY',
  hk: 'HKD',
  us: 'USD',
};

const METRIC_ROWS: EntityKeyMetric['labelKey'][][] = [
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

/** True when rolling 4-quarter net profit is negative (TTM PE is loss-making). */
export function isEntityTtmPeLoss(
  finRows: StockFinIndicatorRow[],
  market?: MarketCode | null,
): boolean {
  const rollingTtmProfit = resolveRollingTtmNetProfit(finRows, market);
  return rollingTtmProfit != null && rollingTtmProfit < 0;
}

function resolveCurrency(currency?: string | null): string | undefined {
  const code = currency?.trim();
  return code || undefined;
}

function resolveWeek52Range(bars: EntityKlineBar[]): { high: number; low: number } | null {
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

export function buildEntityKeyMetrics(input: {
  finRows: StockFinIndicatorRow[];
  klineBars: EntityKlineBar[];
  peBandPoints?: EntityPeBandPoint[];
  chartAnchorDate?: string | null;
  market?: MarketCode | null;
  currency?: string | null;
  peLossLabel?: string;
  /** Live quote fields for market cap / shares / turnover (preferred over fin snapshots). */
  quoteDetail?: Pick<
    CoreTickerQuoteResponse,
    'market_cap' | 'total_shares' | 'pb' | 'turn_rate' | 'volume' | 'dividend_yield' | 'pe'
  > | null;
}): EntityKeyMetric[][] {
  const currency = resolveCurrency(input.currency ?? (input.market ? MARKET_CURRENCY[input.market] : null));
  const latestRawFin = latestFinRow(input.finRows);
  const periodFin = resolveHkPeriodFinRow(input.finRows, input.market);
  const latestBar = input.klineBars.at(-1) ?? null;
  const lastClose = latestBar && latestBar.close > 0 ? latestBar.close : null;

  // Live valuation only — never prefer quarterly fin total_market_cap / hksk_market_cap.
  const marketCap =
    isValidNumber(input.quoteDetail?.market_cap)
      ? input.quoteDetail.market_cap
      : isValidNumber(input.quoteDetail?.total_shares) && lastClose != null
        ? input.quoteDetail.total_shares * lastClose
        : null;
  const totalShares =
    isValidNumber(input.quoteDetail?.total_shares)
      ? input.quoteDetail.total_shares
      : marketCap != null && lastClose != null
        ? marketCap / lastClose
        : null;
  const rollingTtmProfit = resolveRollingTtmNetProfit(input.finRows, input.market);
  let peTtm: number | null = null;
  if (rollingTtmProfit != null && rollingTtmProfit < 0) {
    if (marketCap != null) {
      peTtm = marketCap / rollingTtmProfit;
    } else if (totalShares != null && lastClose != null) {
      peTtm = (totalShares * lastClose) / rollingTtmProfit;
    }
  } else if (marketCap != null && rollingTtmProfit != null && rollingTtmProfit > 0) {
    peTtm = marketCap / rollingTtmProfit;
  } else if (
    rollingTtmProfit != null &&
    rollingTtmProfit > 0 &&
    totalShares != null &&
    lastClose != null
  ) {
    peTtm = (totalShares * lastClose) / rollingTtmProfit;
  } else {
    peTtm = resolvePeBandPeForDate(input.peBandPoints ?? [], input.chartAnchorDate);
  }

  const quotePe = input.quoteDetail?.pe;
  const peDynamic =
    quotePe != null && Number.isFinite(quotePe) && quotePe !== 0 ? quotePe : null;

  const pb =
    isValidSignedNumber(latestRawFin?.pb_ttm)
      ? latestRawFin.pb_ttm
      : isValidSignedNumber(input.quoteDetail?.pb)
        ? input.quoteDetail.pb
        : null;
  const epsBasic = isValidSignedNumber(periodFin?.eps_basic) ? periodFin.eps_basic : null;
  const roe = isValidSignedNumber(periodFin?.roe_weighted) ? periodFin.roe_weighted : null;
  const roa = isValidSignedNumber(periodFin?.roa) ? periodFin.roa : null;
  const grossMargin = isValidSignedNumber(latestRawFin?.gross_margin) ? latestRawFin.gross_margin : null;
  const netMargin = isValidSignedNumber(latestRawFin?.net_margin) ? latestRawFin.net_margin : null;
  const dividendYield =
    isValidNumber(input.quoteDetail?.dividend_yield)
      ? input.quoteDetail.dividend_yield
      : isValidNumber(latestRawFin?.dividend_rate)
        ? latestRawFin.dividend_rate
        : null;
  const week52 = resolveWeek52Range(input.klineBars);
  const volume =
    latestBar?.volume != null && Number.isFinite(latestBar.volume) && latestBar.volume > 0
      ? latestBar.volume
      : input.quoteDetail?.volume != null &&
          Number.isFinite(input.quoteDetail.volume) &&
          input.quoteDetail.volume > 0
        ? input.quoteDetail.volume
        : null;
  const turnover =
    resolveTurnoverRate(volume, totalShares) ??
    (isValidNumber(input.quoteDetail?.turn_rate) ? input.quoteDetail.turn_rate : null);

  const byKey: Record<string, EntityKeyMetric> = {
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
