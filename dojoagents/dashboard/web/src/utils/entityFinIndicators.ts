import type { MarketCode } from '../types/market';
import type {
  EntityFinancialYear,
  EntityProfitabilityAxis,
  StockFinIndicatorRow,
} from '../types/entity';

export const REVENUE_CHART_YOY_BASELINE_START = '2022-01-01';
export const REVENUE_CHART_DISPLAY_FROM_YEAR = 2024;

type ComparableQuarter = 'q1' | 'q2' | 'q3' | 'q4';

const REVENUE_CHART_DISPLAY_FROM_QUARTER: ComparableQuarter = 'q1';

type HkPeriodKind = 'q1' | 'interim' | 'q3' | 'annual';

const HK_PERIOD_PREVIOUS: Record<HkPeriodKind, HkPeriodKind | null> = {
  q1: null,
  interim: 'q1',
  q3: 'interim',
  annual: 'q3',
};

/** Disclosure date (natural calendar); std_report_date is fiscal period-end only. */
export function extractReportDate(row: StockFinIndicatorRow): string {
  const raw = row.report_date || row.std_report_date || '';
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
  q2: 'Q2',
  q3: 'Q3',
  q4: 'Q4',
};

const UNIFIED_AXIS_LABEL_RE = /^\d{2}Q[1-4]$/;

/** Unified revenue-chart axis label from backend calendar fields. */
export function unifiedFinPeriodAxisLabel(row: StockFinIndicatorRow): string {
  if (row.calendar_period_label) return row.calendar_period_label;
  const meta = calendarPeriodFromRow(row);
  if (meta) {
    return `${meta.fiscalYear.slice(2)}${QUARTER_SUFFIX[meta.quarter]}`;
  }
  return shortFinPeriodLabel(periodLabel(row));
}

/** Compact axis label, e.g. 2024年中报 → 24Q2; 2024-06-30 → 24Q2 */
export function shortFinPeriodLabel(label: string, _locale: 'zh' | 'en' = 'zh'): string {
  if (UNIFIED_AXIS_LABEL_RE.test(label)) return label;

  const isoDate = label.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (isoDate) {
    const quarter = REPORT_DATE_TO_QUARTER[`${isoDate[2]}-${isoDate[3]}`];
    if (quarter) {
      return `${isoDate[1].slice(2)}${QUARTER_SUFFIX[quarter]}`;
    }
  }

  const named = label.match(/^(\d{4})年?(.+)$/);
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

const QUARTER_ORDER: Record<ComparableQuarter, number> = {
  q1: 1,
  q2: 2,
  q3: 3,
  q4: 4,
};

const CALENDAR_QUARTER_FROM_NUM: Record<number, ComparableQuarter> = {
  1: 'q1',
  2: 'q2',
  3: 'q3',
  4: 'q4',
};

function calendarPeriodFromRow(
  row: StockFinIndicatorRow,
  market?: MarketCode | string | null,
): CalendarPeriod | null {
  if (row.calendar_year != null && row.calendar_quarter != null) {
    const quarter = CALENDAR_QUARTER_FROM_NUM[row.calendar_quarter];
    if (quarter) {
      return { fiscalYear: String(row.calendar_year), quarter };
    }
  }
  return comparableQuarter(row, market);
}

function sortFinRows(items: StockFinIndicatorRow[]): StockFinIndicatorRow[] {
  return [...items].sort((a, b) => {
    const ai = a.calendar_period_index;
    const bi = b.calendar_period_index;
    if (ai != null && bi != null && ai !== bi) return ai - bi;
    if (ai != null && bi == null) return -1;
    if (ai == null && bi != null) return 1;

    const ma = calendarPeriodFromRow(a);
    const mb = calendarPeriodFromRow(b);
    if (ma && mb) {
      if (ma.fiscalYear !== mb.fiscalYear) return ma.fiscalYear.localeCompare(mb.fiscalYear);
      const byQuarter = QUARTER_ORDER[ma.quarter] - QUARTER_ORDER[mb.quarter];
      if (byQuarter !== 0) return byQuarter;
    }

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

/** Fiscal period-end date when present (not used for natural-calendar axis). */
function extractStdReportDate(row: StockFinIndicatorRow): string {
  const raw = row.std_report_date || '';
  const text = String(raw).trim();
  if (!text) return '';
  if (text.includes('T')) return text.split('T', 1)[0] ?? text;
  if (text.includes(' ')) return text.split(' ', 1)[0] ?? text;
  return text.slice(0, 10);
}

function parseIsoDateMs(date: string): number | null {
  if (date.length < 10) return null;
  const ms = Date.parse(`${date.slice(0, 10)}T00:00:00Z`);
  return Number.isFinite(ms) ? ms : null;
}

type CalendarPeriod = { fiscalYear: string; quarter: ComparableQuarter };

const FISCAL_TO_CALENDAR_QUARTER_OFFSET = 2;

function fiscalPeriodFromName(row: StockFinIndicatorRow): CalendarPeriod | null {
  const name = row.report_period_name?.trim() ?? '';
  const named = name.match(/^(\d{4})年?(.+)$/);
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

  return null;
}

function quarterToIndex(year: string, quarter: ComparableQuarter): number {
  const order: Record<ComparableQuarter, number> = { q1: 0, q2: 1, q3: 2, q4: 3 };
  return Number(year) * 4 + order[quarter];
}

function indexToQuarter(index: number): CalendarPeriod {
  const quarters: ComparableQuarter[] = ['q1', 'q2', 'q3', 'q4'];
  const normalized = ((index % 4) + 4) % 4;
  const year = Math.floor(index / 4);
  return { fiscalYear: String(year), quarter: quarters[normalized] };
}

function shiftCalendarPeriod(base: CalendarPeriod, quarterOffset: number): CalendarPeriod {
  return indexToQuarter(quarterToIndex(base.fiscalYear, base.quarter) + quarterOffset);
}

function stdAlignedCalendarPeriod(
  disclosure: string,
  std: string,
): CalendarPeriod | null {
  if (std.length < 10) return null;
  const stdQuarter = REPORT_DATE_TO_QUARTER[std.slice(5)];
  if (!stdQuarter) return null;

  const stdMs = parseIsoDateMs(std);
  const disclosureMs = parseIsoDateMs(disclosure);
  if (stdMs != null && disclosureMs != null) {
    const daysAfter = (disclosureMs - stdMs) / 86_400_000;
    if (daysAfter >= -5 && daysAfter <= 45) {
      return { fiscalYear: std.slice(0, 4), quarter: stdQuarter };
    }
  }
  if (disclosure === std) {
    return { fiscalYear: std.slice(0, 4), quarter: stdQuarter };
  }
  return null;
}

function periodEndCalendarPeriod(disclosure: string, std: string): CalendarPeriod | null {
  if (disclosure.length < 10) return null;
  const quarter = REPORT_DATE_TO_QUARTER[disclosure.slice(5, 10)];
  if (!quarter) return null;
  if (std && std.slice(0, 10) !== disclosure.slice(0, 10)) return null;
  return { fiscalYear: disclosure.slice(0, 4), quarter };
}

function fiscalToCalendarOffset(
  market: MarketCode | string | null | undefined,
  disclosure: string,
  std: string,
): number {
  const code = (market ?? '').toLowerCase();
  if (code === 'cn' || code === 'hk') return 0;
  if (code === 'us') return FISCAL_TO_CALENDAR_QUARTER_OFFSET;
  if (periodEndCalendarPeriod(disclosure, std)) return 0;
  return FISCAL_TO_CALENDAR_QUARTER_OFFSET;
}

/** Fiscal label from report_period_name; US adds +2 quarters when report_date is disclosure. */
function comparableQuarter(
  row: StockFinIndicatorRow,
  market?: MarketCode | string | null,
): CalendarPeriod | null {
  const disclosure = extractReportDate(row);
  if (disclosure.length < 4) return null;

  const std = extractStdReportDate(row);
  const aligned = stdAlignedCalendarPeriod(disclosure, std);
  if (aligned) return aligned;

  const periodEnd = periodEndCalendarPeriod(disclosure, std);
  if (periodEnd) return periodEnd;

  const fiscal = fiscalPeriodFromName(row);
  if (!fiscal) return null;

  const offset = fiscalToCalendarOffset(market, disclosure, std);
  if (offset === 0) return fiscal;
  return shiftCalendarPeriod(fiscal, offset);
}

function hkPeriodKind(row: StockFinIndicatorRow): { fiscalYear: string; kind: HkPeriodKind } | null {
  const comparable = calendarPeriodFromRow(row);
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
    const meta = calendarPeriodFromRow(row);
    if (!meta) continue;
    const revenue = row.total_operating_revenue;
    if (revenue == null || Number.isNaN(revenue)) continue;
    revenueByQuarter.set(`${meta.fiscalYear}:${meta.quarter}`, revenue);
  }

  const yoyByLabel = new Map<string, number | null>();
  for (const row of rows) {
    const label = periodLabel(row);
    const meta = calendarPeriodFromRow(row);
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

/** Chart display starts at 2024 Q1 using backend calendar fields. */
function filterRowsForRevenueDisplay(rows: StockFinIndicatorRow[]): StockFinIndicatorRow[] {
  const minIndex = quarterToIndex(String(REVENUE_CHART_DISPLAY_FROM_YEAR), REVENUE_CHART_DISPLAY_FROM_QUARTER);
  return rows.filter((row) => {
    if (row.calendar_period_index != null) {
      return row.calendar_period_index >= minIndex;
    }
    const meta = calendarPeriodFromRow(row);
    if (!meta) return false;
    return quarterToIndex(meta.fiscalYear, meta.quarter) >= minIndex;
  });
}

export function mapFinIndicatorsToFinancials(
  items: StockFinIndicatorRow[],
  market?: MarketCode | string | null,
): EntityFinancialYear[] {
  const normalizedMarket = market?.toLowerCase?.() ?? market;
  // HK accumulate rows are de-accumulated here only (API returns raw cumulative data).
  const sourceItems =
    normalizedMarket === 'hk' ? deaccumulateHkFinRows(items) : items;
  const sorted = sortFinRows(sourceItems);
  const yoyByLabel = computeSameQuarterRevenueYoY(sorted);
  const slice = filterRowsForRevenueDisplay(sorted);

  return slice.map((row) => {
    const label = periodLabel(row);
    const axisLabel = row.calendar_period_label ?? unifiedFinPeriodAxisLabel(row);
    return {
      year: axisLabel,
      reportDate: extractReportDate(row),
      revenue: toNumber(row.total_operating_revenue),
      netProfit: toNumber(row.net_profit_attr_parent),
      revenueYoY: yoyByLabel.get(label) ?? null,
    };
  });
}

export function mapFinIndicatorsToProfitability(items: StockFinIndicatorRow[]): EntityProfitabilityAxis[] {
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

export function isQuarterlyFinRow(row: StockFinIndicatorRow): boolean {
  return String(row.report_type ?? '').trim().toLowerCase() === 'quarter';
}

/** Sum net profit from the latest four distinct quarterly reports. */
export function resolveRollingTtmNetProfit(
  rows: StockFinIndicatorRow[],
  market?: MarketCode | string | null,
): number | null {
  const quarterlyRows = rows.filter((row) => calendarPeriodFromRow(row, market) != null);
  const sorted = [...sortFinRows(quarterlyRows)].reverse();
  const seen = new Set<number>();
  let sum = 0;
  let count = 0;
  for (const row of sorted) {
    const period = calendarPeriodFromRow(row, market);
    if (!period) continue;
    const index = quarterToIndex(period.fiscalYear, period.quarter);
    if (seen.has(index)) continue;
    const profit = row.net_profit_attr_parent;
    if (profit == null || !Number.isFinite(profit)) continue;
    seen.add(index);
    sum += profit;
    count += 1;
    if (count >= 4) break;
  }
  return count >= 4 ? sum : null;
}
