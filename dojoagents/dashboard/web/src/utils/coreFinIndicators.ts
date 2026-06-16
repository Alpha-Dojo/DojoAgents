import type { MarketCode } from '../types/dojoMesh';
import type {
  CoreFinancialYear,
  CoreProfitabilityAxis,
  StockFinIndicatorRow,
} from '../types/dojoCore';

export const DEFAULT_REVENUE_CHART_YEARS = 3;

type HkPeriodKind = 'q1' | 'interim' | 'q3' | 'annual';

const HK_PERIOD_PREVIOUS: Record<HkPeriodKind, HkPeriodKind | null> = {
  q1: null,
  interim: 'q1',
  q3: 'interim',
  annual: 'q3',
};

export function extractReportDate(row: StockFinIndicatorRow): string {
  const raw = row.std_report_date || row.report_date || '';
  const text = String(raw).trim();
  if (!text) return '';
  if (text.includes('T')) return text.split('T', 1)[0] ?? text;
  if (text.includes(' ')) return text.split(' ', 1)[0] ?? text;
  return text.slice(0, 10);
}

function periodLabel(row: StockFinIndicatorRow): string {
  const name = row.report_period_name?.trim();
  if (name) return name;
  const date = extractReportDate(row);
  return date || row.symbol;
}

type ComparableQuarter = 'q1' | 'q2' | 'q3' | 'q4';

const SEASON_LABEL_TO_QUARTER: Record<string, ComparableQuarter> = {
  一季度: 'q1',
  二季度: 'q2',
  三季度: 'q3',
  四季度: 'q4',
};

const REPORT_SUFFIX_TO_QUARTER: Array<{ pattern: RegExp; quarter: ComparableQuarter }> = [
  { pattern: /一季报|第一季报/, quarter: 'q1' },
  { pattern: /中报|第二季报|二季度|半年/, quarter: 'q2' },
  { pattern: /三季报|第三季报|三季度/, quarter: 'q3' },
  { pattern: /年报|第四季报|四季度/, quarter: 'q4' },
];

const REPORT_DATE_TO_QUARTER: Record<string, ComparableQuarter> = {
  '03-31': 'q1',
  '06-30': 'q2',
  '09-30': 'q3',
  '12-31': 'q4',
};

const QUARTER_SUFFIX: Record<ComparableQuarter, string> = {
  q1: 'Q1',
  q2: 'H1',
  q3: 'Q3',
  q4: 'FY',
};

const UNIFIED_AXIS_LABEL_RE = /^\d{2}(Q1|H1|Q3|FY)$/;

/** Unified revenue-chart axis label: 24H1, 24Q3, … regardless of market. */
export function unifiedFinPeriodAxisLabel(row: StockFinIndicatorRow): string {
  const meta = comparableQuarter(row);
  if (meta) {
    return `${meta.fiscalYear.slice(2)}${QUARTER_SUFFIX[meta.quarter]}`;
  }
  return shortFinPeriodLabel(periodLabel(row));
}

/** Compact axis label, e.g. 2024年中报 → 24H1; 2024-06-30 → 24H1 */
export function shortFinPeriodLabel(label: string, _locale: 'zh' | 'en' = 'zh'): string {
  if (UNIFIED_AXIS_LABEL_RE.test(label)) return label;

  const isoDate = label.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (isoDate) {
    const quarter = REPORT_DATE_TO_QUARTER[`${isoDate[2]}-${isoDate[3]}`];
    if (quarter) {
      return `${isoDate[1].slice(2)}${QUARTER_SUFFIX[quarter]}`;
    }
  }

  const named = label.match(/^(\d{4})年(.+)$/);
  if (named) {
    for (const { pattern, quarter } of REPORT_SUFFIX_TO_QUARTER) {
      if (pattern.test(named[2])) {
        return `${named[1].slice(2)}${QUARTER_SUFFIX[quarter]}`;
      }
    }
  }

  if (label.length > 9) return label.slice(2);
  return label;
}

function sortFinRows(items: StockFinIndicatorRow[]): StockFinIndicatorRow[] {
  return [...items].sort((a, b) => {
    const da = extractReportDate(a);
    const db = extractReportDate(b);
    if (da !== db) return da.localeCompare(db);
    return periodLabel(a).localeCompare(periodLabel(b));
  });
}

function toNumber(value: number | null | undefined, fallback = 0): number {
  if (value == null || Number.isNaN(value)) return fallback;
  return value;
}

function comparableQuarter(row: StockFinIndicatorRow): { fiscalYear: string; quarter: ComparableQuarter } | null {
  const name = row.report_period_name?.trim() ?? '';
  const named = name.match(/^(\d{4})年(.+)$/);
  if (named) {
    for (const { pattern, quarter } of REPORT_SUFFIX_TO_QUARTER) {
      if (pattern.test(named[2])) {
        return { fiscalYear: named[1], quarter };
      }
    }
  }

  const season = row.season_label?.trim();
  if (season && SEASON_LABEL_TO_QUARTER[season]) {
    const date = extractReportDate(row);
    if (date.length >= 4) {
      return { fiscalYear: date.slice(0, 4), quarter: SEASON_LABEL_TO_QUARTER[season] };
    }
  }

  const date = extractReportDate(row);
  if (date.length >= 10) {
    const quarter = REPORT_DATE_TO_QUARTER[date.slice(5)];
    if (quarter) {
      return { fiscalYear: date.slice(0, 4), quarter };
    }
  }

  return null;
}

function hkPeriodKind(row: StockFinIndicatorRow): { fiscalYear: string; kind: HkPeriodKind } | null {
  const comparable = comparableQuarter(row);
  if (!comparable) return null;
  const kindMap: Record<ComparableQuarter, HkPeriodKind> = {
    q1: 'q1',
    q2: 'interim',
    q3: 'q3',
    q4: 'annual',
  };
  return { fiscalYear: comparable.fiscalYear, kind: kindMap[comparable.quarter] };
}

function computeSameQuarterRevenueYoY(rows: StockFinIndicatorRow[]): Map<string, number | null> {
  const revenueByQuarter = new Map<string, number>();
  for (const row of rows) {
    const meta = comparableQuarter(row);
    if (!meta) continue;
    const revenue = row.total_operating_revenue;
    if (revenue == null || Number.isNaN(revenue)) continue;
    revenueByQuarter.set(`${meta.fiscalYear}:${meta.quarter}`, revenue);
  }

  const yoyByLabel = new Map<string, number | null>();
  for (const row of rows) {
    const label = periodLabel(row);
    const meta = comparableQuarter(row);
    if (!meta) {
      yoyByLabel.set(label, null);
      continue;
    }

    const prevYear = String(Number(meta.fiscalYear) - 1);
    const prevRevenue = revenueByQuarter.get(`${prevYear}:${meta.quarter}`);
    const currentRevenue = row.total_operating_revenue;
    if (prevRevenue == null || prevRevenue === 0 || currentRevenue == null) {
      yoyByLabel.set(label, null);
      continue;
    }

    yoyByLabel.set(label, ((currentRevenue - prevRevenue) / prevRevenue) * 100);
  }

  return yoyByLabel;
}

function subtractMetric(
  current: number | null | undefined,
  previous: number | null | undefined,
): number | null {
  if (current == null) return null;
  if (previous == null) return current;
  return current - previous;
}

export function deaccumulateHkFinRows(items: StockFinIndicatorRow[]): StockFinIndicatorRow[] {
  const sorted = sortFinRows(items);
  const byFyPeriod = new Map<string, StockFinIndicatorRow>();

  for (const row of sorted) {
    const meta = hkPeriodKind(row);
    if (!meta) continue;
    byFyPeriod.set(`${meta.fiscalYear}:${meta.kind}`, row);
  }

  return sorted.map((row) => {
    const meta = hkPeriodKind(row);
    if (!meta) return row;

    const previousKind = HK_PERIOD_PREVIOUS[meta.kind];
    if (!previousKind) return row;

    const previous = byFyPeriod.get(`${meta.fiscalYear}:${previousKind}`);
    if (!previous) return row;

    return {
      ...row,
      total_operating_revenue: subtractMetric(
        row.total_operating_revenue,
        previous.total_operating_revenue,
      ),
      net_profit_attr_parent: subtractMetric(
        row.net_profit_attr_parent,
        previous.net_profit_attr_parent,
      ),
    };
  });
}

/** Latest fin row with HK single-period eps / roe / roa (cumulative rows differenced). */
export function resolveHkPeriodFinRow(
  items: StockFinIndicatorRow[],
  market: MarketCode | string | null | undefined,
): StockFinIndicatorRow | null {
  const sorted = sortFinRows(items);
  const latest = sorted.at(-1);
  if (!latest) return null;
  if ((market ?? '').toLowerCase() !== 'hk') return latest;

  const byFyPeriod = new Map<string, StockFinIndicatorRow>();
  for (const row of sorted) {
    const meta = hkPeriodKind(row);
    if (!meta) continue;
    byFyPeriod.set(`${meta.fiscalYear}:${meta.kind}`, row);
  }

  const meta = hkPeriodKind(latest);
  if (!meta) return latest;

  const previousKind = HK_PERIOD_PREVIOUS[meta.kind];
  if (!previousKind) return latest;

  const previous = byFyPeriod.get(`${meta.fiscalYear}:${previousKind}`);
  if (!previous) return latest;

  return {
    ...latest,
    eps_basic: subtractMetric(latest.eps_basic, previous.eps_basic),
    roe_weighted: subtractMetric(latest.roe_weighted, previous.roe_weighted),
    roa: subtractMetric(latest.roa, previous.roa),
  };
}

function pseudoPercentile(value: number, max: number): number {
  if (max <= 0) return 0;
  return Math.max(0, Math.min(100, (value / max) * 100));
}

function filterRowsWithinRecentYears(
  rows: StockFinIndicatorRow[],
  years: number,
): StockFinIndicatorRow[] {
  if (!rows.length || years <= 0) return rows;

  const latestDate = extractReportDate(rows[rows.length - 1]);
  if (latestDate.length < 4) return rows;

  const latestYear = Number(latestDate.slice(0, 4));
  if (!Number.isFinite(latestYear)) return rows;

  const minYear = latestYear - years + 1;
  return rows.filter((row) => {
    const date = extractReportDate(row);
    if (date.length < 4) return false;
    const year = Number(date.slice(0, 4));
    return Number.isFinite(year) && year >= minYear;
  });
}

export function mapFinIndicatorsToFinancials(
  items: StockFinIndicatorRow[],
  years = DEFAULT_REVENUE_CHART_YEARS,
  market?: MarketCode | string | null,
): CoreFinancialYear[] {
  const normalizedMarket = market?.toLowerCase?.() ?? market;
  // HK accumulate rows are de-accumulated here only (API returns raw cumulative data).
  const sourceItems =
    normalizedMarket === 'hk' ? deaccumulateHkFinRows(items) : items;
  const sorted = sortFinRows(sourceItems);
  const yoyByLabel = computeSameQuarterRevenueYoY(sorted);
  const slice = filterRowsWithinRecentYears(sorted, years);
  return slice.map((row) => {
    const label = periodLabel(row);
    const axisLabel = unifiedFinPeriodAxisLabel(row);
    return {
      year: axisLabel,
      revenue: toNumber(row.total_operating_revenue),
      netProfit: toNumber(row.net_profit_attr_parent),
      revenueYoY: yoyByLabel.get(label) ?? null,
    };
  });
}

export function mapFinIndicatorsToProfitability(items: StockFinIndicatorRow[]): CoreProfitabilityAxis[] {
  const sorted = sortFinRows(items);
  const latest = sorted[sorted.length - 1];
  if (!latest) return [];

  const gross = toNumber(latest.gross_margin);
  const net = toNumber(latest.net_margin);
  const roe = toNumber(latest.roe_weighted);
  const roa = toNumber(latest.roa);

  return [
    {
      key: 'grossMargin',
      value: gross,
      max: 100,
      percentile: pseudoPercentile(gross, 100),
      beatsLabelKey: 'beats50',
    },
    {
      key: 'netMargin',
      value: net,
      max: 100,
      percentile: pseudoPercentile(net, 100),
      beatsLabelKey: 'beats50',
    },
    {
      key: 'roe',
      value: roe,
      max: 35,
      percentile: pseudoPercentile(roe, 35),
      beatsLabelKey: 'beats50',
    },
    {
      key: 'roa',
      value: roa,
      max: 25,
      percentile: pseudoPercentile(roa, 25),
      beatsLabelKey: 'beats50',
    },
  ];
}
