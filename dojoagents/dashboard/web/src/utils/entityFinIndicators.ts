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

const HK_REPORT_PERIOD_RE = /^(\d{4})年(一季报|中报|三季报|年报)$/;

const HK_PERIOD_NAME_TO_KIND: Record<string, HkPeriodKind> = {
  一季报: 'q1',
  中报: 'interim',
  三季报: 'q3',
  年报: 'annual',
};

const STD_REPORT_DATE_TO_HK_KIND: Record<string, HkPeriodKind> = {
  '03-31': 'q1',
  '06-30': 'interim',
  '09-30': 'q3',
  '12-31': 'annual',
};

function isoDateOnly(raw: string | null | undefined): string {
  const text = String(raw ?? '').trim();
  if (!text) return '';
  if (text.includes('T')) return text.split('T', 1)[0] ?? text;
  if (text.includes(' ')) return text.split(' ', 1)[0] ?? text;
  return text.slice(0, 10);
}

/**
 * Sort / legacy date: prefer actual period-end (report_date), then vendor calendarized std.
 */
export function extractReportDate(row: StockFinIndicatorRow): string {
  return isoDateOnly(row.report_date) || isoDateOnly(row.std_report_date);
}

/** Actual fiscal period-end date. */
export function extractPeriodEndDate(row: StockFinIndicatorRow): string {
  return isoDateOnly(row.report_date) || isoDateOnly(row.std_report_date);
}

/**
 * Filing / publication date for earnings-season natural-quarter mapping.
 * Prefers public_date; falls back to report_date only when public_date is absent (e.g. HK).
 */
export function extractDisclosureDate(row: StockFinIndicatorRow): string {
  return isoDateOnly(row.public_date) || isoDateOnly(row.report_date);
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

/** Unified revenue-chart axis label from the filing period (report_period_name). */
export function unifiedFinPeriodAxisLabel(
  row: StockFinIndicatorRow,
  _market?: MarketCode | string | null,
  _seriesOffset?: number,
): string {
  const meta = reportFiscalPeriod(row);
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

function calendarPeriodFromRow(
  row: StockFinIndicatorRow,
  _market?: MarketCode | string | null,
  _seriesOffset?: number,
): CalendarPeriod | null {
  return reportFiscalPeriod(row);
}

function sortFinRows(
  items: StockFinIndicatorRow[],
  market?: MarketCode | string | null,
  _seriesOffset?: number,
): StockFinIndicatorRow[] {
  return [...items].sort((a, b) => {
    const ma = revenueComparablePeriod(a, market);
    const mb = revenueComparablePeriod(b, market);
    if (ma && mb) {
      if (ma.fiscalYear !== mb.fiscalYear) return ma.fiscalYear.localeCompare(mb.fiscalYear);
      const byQuarter = QUARTER_ORDER[ma.quarter] - QUARTER_ORDER[mb.quarter];
      if (byQuarter !== 0) return byQuarter;
    }

    const da = extractDisclosureDate(a) || extractStdReportDate(a);
    const db = extractDisclosureDate(b) || extractStdReportDate(b);
    if (da !== db) return da.localeCompare(db);
    return periodLabel(a).localeCompare(periodLabel(b));
  });
}

function sortHkFinRowsForDeaccumulate(items: StockFinIndicatorRow[]): StockFinIndicatorRow[] {
  return [...items].sort((a, b) => {
    const da = extractStdReportDate(a) || extractReportDate(a);
    const db = extractStdReportDate(b) || extractReportDate(b);
    if (da !== db) return da.localeCompare(db);
    return periodLabel(a).localeCompare(periodLabel(b));
  });
}

function toNumber(value: number | null | undefined, fallback = 0): number {
  if (value == null || Number.isNaN(value)) return fallback;
  return value;
}

/** Fiscal period-end date when present (vendor calendarized label date). */
function extractStdReportDate(row: StockFinIndicatorRow): string {
  return isoDateOnly(row.std_report_date);
}

type CalendarPeriod = { fiscalYear: string; quarter: ComparableQuarter };

const CALENDAR_QUARTER_BY_MONTH_INDEX: ComparableQuarter[] = ['q1', 'q2', 'q3', 'q4'];

/** Short post-period gap: fiscal label already aligns with natural calendar. */
const SHORT_PERIOD_LAG_DAYS = 45;
/** Days per quarter when converting period-end vs vendor-calendarized std gap into Q diff. */
const CALENDAR_QUARTER_DAYS = 90;

/** Calendar quarter that contains an ISO date (Jan–Mar = Q1 … Oct–Dec = Q4). */
function calendarQuarterFromIsoDate(date: string): CalendarPeriod | null {
  if (date.length < 7) return null;
  const year = date.slice(0, 4);
  const month = Number(date.slice(5, 7));
  if (!Number.isFinite(month) || month < 1 || month > 12) return null;
  const quarter = CALENDAR_QUARTER_BY_MONTH_INDEX[Math.floor((month - 1) / 3)];
  return { fiscalYear: year, quarter };
}

/**
 * Natural quarter for an Apr/May/Jun period signal: always Q1 of that year.
 * (Reports associated with Apr–Jun land on natural Q1 — never Q2.)
 */
function naturalQuarterForAprToJunSignal(date: string): CalendarPeriod | null {
  if (date.length < 7) return null;
  const year = Number(date.slice(0, 4));
  const month = Number(date.slice(5, 7));
  if (!Number.isFinite(year) || !Number.isFinite(month) || month < 4 || month > 6) return null;
  return { fiscalYear: String(year), quarter: 'q1' };
}

function fiscalPeriodFromReport(row: StockFinIndicatorRow): CalendarPeriod | null {
  return fiscalPeriodFromName(row);
}

function daysBetweenIsoDates(start: string, end: string): number | null {
  if (start.length < 10 || end.length < 10) return null;
  const startMs = Date.parse(`${start.slice(0, 10)}T00:00:00Z`);
  const endMs = Date.parse(`${end.slice(0, 10)}T00:00:00Z`);
  if (!Number.isFinite(startMs) || !Number.isFinite(endMs)) return null;
  return Math.round((endMs - startMs) / 86_400_000);
}

/**
 * Per-row (natural − fiscal) from period-end vs report_period_name.
 *
 * - Prefer report_date as actual fiscal period-end (not public_date).
 * - When period-end is before vendor std_report_date (AAPL / ADBE style):
 *   Apr–Jun → natural Q1; otherwise containment calendar quarter.
 * - When period-end is after std: short lag → 0; else floor(lagDays / 90)
 *   (floor, not round — May FYE ~151d → 1Q, June FYE ~181d → 2Q).
 */
function detectFiscalToNaturalOffset(row: StockFinIndicatorRow): number {
  const fiscal = fiscalPeriodFromReport(row);
  if (!fiscal) return 0;

  const periodEnd = extractPeriodEndDate(row);
  if (periodEnd.length < 10) return 0;

  const stdDate = extractStdReportDate(row);
  if (stdDate.length >= 10 && periodEnd < stdDate) {
    const aprJun = naturalQuarterForAprToJunSignal(periodEnd);
    const natural = aprJun ?? calendarQuarterFromIsoDate(periodEnd);
    if (!natural) return 0;
    return (
      quarterToIndex(natural.fiscalYear, natural.quarter) -
      quarterToIndex(fiscal.fiscalYear, fiscal.quarter)
    );
  }

  const lagDays = stdDate.length >= 10 ? daysBetweenIsoDates(stdDate, periodEnd) : null;
  if (lagDays == null) {
    const aprJun = naturalQuarterForAprToJunSignal(periodEnd);
    const natural = aprJun ?? calendarQuarterFromIsoDate(periodEnd);
    if (!natural) return 0;
    return (
      quarterToIndex(natural.fiscalYear, natural.quarter) -
      quarterToIndex(fiscal.fiscalYear, fiscal.quarter)
    );
  }

  if (lagDays <= SHORT_PERIOD_LAG_DAYS) return 0;
  return Math.max(1, Math.floor(lagDays / CALENDAR_QUARTER_DAYS));
}

function sortRowsByPeriodEnd(rows: StockFinIndicatorRow[]): StockFinIndicatorRow[] {
  return [...rows].sort((a, b) => {
    const da = extractPeriodEndDate(a) || extractStdReportDate(a);
    const db = extractPeriodEndDate(b) || extractStdReportDate(b);
    if (da !== db) return da.localeCompare(db);
    return periodLabel(a).localeCompare(periodLabel(b));
  });
}

/** Series-level offset: mode of per-row diffs (unchanged approach). */
export function resolveFiscalToNaturalOffset(rows: StockFinIndicatorRow[]): number {
  const counts = new Map<number, number>();
  for (const row of rows) {
    const offset = detectFiscalToNaturalOffset(row);
    counts.set(offset, (counts.get(offset) ?? 0) + 1);
  }
  let best = 0;
  let bestCount = -1;
  for (const [offset, count] of counts) {
    if (count > bestCount) {
      best = offset;
      bestCount = count;
    }
  }
  return best;
}

/**
 * Title badge (自然年 − 财年): prefer the latest period's optimized diff so
 * 「最新财年 + diff」 matches the newest bar; fall back to series mode.
 */
export function resolveNaturalMinusFiscalQuarters(
  rows: StockFinIndicatorRow[],
): number | null {
  if (!rows.length) return null;

  const sorted = sortRowsByPeriodEnd(rows);
  const latest = sorted[sorted.length - 1];
  const latestOffset = detectFiscalToNaturalOffset(latest);
  if (latestOffset !== 0) return latestOffset;

  const mode = resolveFiscalToNaturalOffset(rows);
  return mode === 0 ? null : mode;
}

/**
 * Filing / fiscal quarter for chart axis, YoY, and sorting.
 * Uses report_period_name as-is (no fiscal→natural shift).
 */
function reportFiscalPeriod(row: StockFinIndicatorRow): CalendarPeriod | null {
  const fiscal = fiscalPeriodFromReport(row);
  if (fiscal) return fiscal;

  const fromStd = calendarQuarterFromIsoDate(extractStdReportDate(row));
  if (fromStd) return fromStd;

  return calendarQuarterFromIsoDate(extractDisclosureDate(row));
}

function fiscalPeriodFromName(row: StockFinIndicatorRow): CalendarPeriod | null {
  const name = row.report_period_name?.trim() ?? '';
  const english = name.match(/^(\d{4})\s*Q([1-4])$/i);
  if (english) {
    return { fiscalYear: english[1], quarter: `q${english[2]}` as ComparableQuarter };
  }
  const englishLead = name.match(/^Q([1-4])\s+(\d{4})$/i);
  if (englishLead) {
    return { fiscalYear: englishLead[2], quarter: `q${englishLead[1]}` as ComparableQuarter };
  }

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

/** HK accumulate rows: period kind from report_period_name, not calendar_* fields. */
function hkReportPeriodKind(row: StockFinIndicatorRow): { fiscalYear: string; kind: HkPeriodKind } | null {
  const name = row.report_period_name?.trim() ?? '';
  const named = name.match(HK_REPORT_PERIOD_RE);
  if (named) {
    const kind = HK_PERIOD_NAME_TO_KIND[named[2]];
    if (kind) return { fiscalYear: named[1], kind };
  }

  const reportDate = extractStdReportDate(row) || extractReportDate(row);
  if (reportDate.length < 10) return null;

  const kind = STD_REPORT_DATE_TO_HK_KIND[reportDate.slice(5, 10)];
  if (!kind) return null;
  return { fiscalYear: reportDate.slice(0, 4), kind };
}

function hkPeriodKind(row: StockFinIndicatorRow): { fiscalYear: string; kind: HkPeriodKind } | null {
  return hkReportPeriodKind(row);
}

function revenueComparablePeriod(
  row: StockFinIndicatorRow,
  _market?: MarketCode | string | null,
  _seriesOffset?: number,
): CalendarPeriod | null {
  return reportFiscalPeriod(row);
}

function todayIsoUtc(): string {
  const today = new Date();
  const year = today.getUTCFullYear();
  const month = String(today.getUTCMonth() + 1).padStart(2, '0');
  const day = String(today.getUTCDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

/** Only include fin rows whose disclosure date (report_date) is on or before today. */
export function isDisclosedFinRow(row: StockFinIndicatorRow): boolean {
  const disclosure = extractDisclosureDate(row);
  if (disclosure.length < 10) return true;
  return disclosure.slice(0, 10) <= todayIsoUtc();
}

function computeSameQuarterRevenueYoY(
  rows: StockFinIndicatorRow[],
  market?: MarketCode | string | null,
  _seriesOffset?: number,
): Map<string, number | null> {
  // Same fiscal quarter only (e.g. 25Q4 vs 24Q4). HK accumulate rows are
  // de-accumulated upstream; do not gate YoY on revenue magnitude heuristics.
  const revenueByQuarter = new Map<string, number>();
  for (const row of rows) {
    const meta = revenueComparablePeriod(row, market);
    if (!meta) continue;
    const revenue = row.total_operating_revenue;
    if (revenue == null || Number.isNaN(revenue)) continue;
    revenueByQuarter.set(`${meta.fiscalYear}:${meta.quarter}`, revenue);
  }

  const yoyByLabel = new Map<string, number | null>();
  for (const row of rows) {
    const label = periodLabel(row);
    const meta = revenueComparablePeriod(row, market);
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

/** Q4-single / full-year ratio from fiscal years with complete annual − Q3 de-accum. */
function medianHkAnnualSingleQuarterRatio(
  byFyPeriod: Map<string, StockFinIndicatorRow>,
): number | null {
  const ratios: number[] = [];
  for (const [key, annualRow] of byFyPeriod) {
    if (!key.endsWith(':annual')) continue;
    const fiscalYear = key.split(':')[0] ?? '';
    const q3Row = byFyPeriod.get(`${fiscalYear}:q3`);
    if (!q3Row) continue;

    const annualRev = annualRow.total_operating_revenue;
    const q3Rev = q3Row.total_operating_revenue;
    if (annualRev == null || q3Rev == null || annualRev <= 0) continue;

    const q4Single = annualRev - q3Rev;
    if (q4Single <= 0 || q4Single >= annualRev) continue;
    ratios.push(q4Single / annualRev);
  }
  if (!ratios.length) return null;

  ratios.sort((a, b) => a - b);
  const mid = Math.floor(ratios.length / 2);
  return ratios.length % 2 === 1 ? ratios[mid] : (ratios[mid - 1] + ratios[mid]) / 2;
}

function scaleMetric(value: number | null | undefined, ratio: number): number | null {
  if (value == null) return null;
  return value * ratio;
}

export function deaccumulateHkFinRows(items: StockFinIndicatorRow[]): StockFinIndicatorRow[] {
  const sorted = sortHkFinRowsForDeaccumulate(items);
  const byFyPeriod = new Map<string, StockFinIndicatorRow>();

  for (const row of sorted) {
    const meta = hkPeriodKind(row);
    if (!meta) continue;
    byFyPeriod.set(`${meta.fiscalYear}:${meta.kind}`, row);
  }

  const annualSingleQuarterRatio = medianHkAnnualSingleQuarterRatio(byFyPeriod);

  return sorted.map((row) => {
    const meta = hkPeriodKind(row);
    if (!meta) return row;

    const previousKind = HK_PERIOD_PREVIOUS[meta.kind];
    if (!previousKind) return row;

    const previous = byFyPeriod.get(`${meta.fiscalYear}:${previousKind}`);
    if (!previous) {
      // API history may start mid-year (e.g. missing 2022 Q3); annual stays cumulative.
      if (meta.kind === 'annual' && annualSingleQuarterRatio != null) {
        return {
          ...row,
          total_operating_revenue: scaleMetric(
            row.total_operating_revenue,
            annualSingleQuarterRatio,
          ),
          net_profit_attr_parent: scaleMetric(
            row.net_profit_attr_parent,
            annualSingleQuarterRatio,
          ),
        };
      }
      return row;
    }

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
  const sorted = sortFinRows(items, market);
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

/** Chart display starts at 2024 Q1; HK uses report_period_name, not calendar_* fields. */
function filterRowsForRevenueDisplay(
  rows: StockFinIndicatorRow[],
  market?: MarketCode | string | null,
  _seriesOffset?: number,
): StockFinIndicatorRow[] {
  const minIndex = quarterToIndex(String(REVENUE_CHART_DISPLAY_FROM_YEAR), REVENUE_CHART_DISPLAY_FROM_QUARTER);
  return rows.filter((row) => {
    if (!isDisclosedFinRow(row)) return false;
    const meta = revenueComparablePeriod(row, market);
    if (!meta) return false;
    return quarterToIndex(meta.fiscalYear, meta.quarter) >= minIndex;
  });
}

/**
 * Quality score for collapsing duplicate IPO / vendor rows that share one fiscal quarter.
 * Prefers name↔std↔period-end consistency and 季报 over 年报 when both map to Q4.
 */
function finRowQualityScore(row: StockFinIndicatorRow): number {
  let score = 0;
  const name = row.report_period_name?.trim() ?? '';
  const fiscal = fiscalPeriodFromName(row);
  const periodEnd = extractPeriodEndDate(row);
  const std = extractStdReportDate(row);

  const isAnnualOnly = /年报/.test(name) && !/第四季报|四季度/.test(name);
  const isQuarterlyFiling = /第?[一二三四]季报|中报|四季度/.test(name);
  if (isQuarterlyFiling && !isAnnualOnly) score += 30;
  else if (isAnnualOnly) score += 10;

  if (fiscal && periodEnd.length >= 10) {
    if (periodEnd.slice(0, 4) === fiscal.fiscalYear) score += 50;
    else score -= 40;
    const peCal = calendarQuarterFromIsoDate(periodEnd);
    if (peCal && peCal.quarter === fiscal.quarter) score += 20;
  }

  if (fiscal && std.length >= 10) {
    if (std.slice(0, 4) === fiscal.fiscalYear) score += 50;
    else score -= 80;
    const stdCal = calendarQuarterFromIsoDate(std);
    if (stdCal && stdCal.quarter === fiscal.quarter) score += 20;
  }

  if (std.length >= 10 && periodEnd.length >= 10) {
    if (std === periodEnd) score += 40;
    else {
      const lag = Math.abs(daysBetweenIsoDates(std, periodEnd) ?? 9_999);
      if (lag <= SHORT_PERIOD_LAG_DAYS) score += 20;
      else if (lag > 370) score -= 100;
    }
  }

  if (row.total_operating_revenue != null && Number.isFinite(row.total_operating_revenue)) {
    score += 5;
  }

  return score;
}

function preferFinRow(a: StockFinIndicatorRow, b: StockFinIndicatorRow): StockFinIndicatorRow {
  const scoreA = finRowQualityScore(a);
  const scoreB = finRowQualityScore(b);
  if (scoreA !== scoreB) return scoreA > scoreB ? a : b;

  const dateA = extractDisclosureDate(a) || extractPeriodEndDate(a);
  const dateB = extractDisclosureDate(b) || extractPeriodEndDate(b);
  if (dateA !== dateB) return dateA >= dateB ? a : b;

  return a;
}

function metricFingerprint(row: StockFinIndicatorRow): string | null {
  const revenue = row.total_operating_revenue;
  const profit = row.net_profit_attr_parent;
  if (revenue == null || !Number.isFinite(revenue)) return null;
  if (profit == null || !Number.isFinite(profit)) return null;
  return `${revenue}|${profit}`;
}

/** True when name / std / period-end years disagree (IPO vendor cross-label pattern). */
function isCrossLabeledSuspect(row: StockFinIndicatorRow): boolean {
  const fiscal = fiscalPeriodFromName(row);
  if (!fiscal) return false;
  const periodEnd = extractPeriodEndDate(row);
  const std = extractStdReportDate(row);
  if (std.length >= 10 && std.slice(0, 4) !== fiscal.fiscalYear) return true;
  if (periodEnd.length >= 10 && periodEnd.slice(0, 4) !== fiscal.fiscalYear) return true;
  if (std.length >= 10 && periodEnd.length >= 10) {
    const lag = Math.abs(daysBetweenIsoDates(std, periodEnd) ?? 0);
    if (lag > 370) return true;
  }
  return false;
}

/**
 * Collapse one API row per comparable fiscal quarter for the revenue chart.
 * Also drops cross-labeled clones that reuse the same revenue+profit under another year label.
 */
export function dedupeFinRowsByComparableQuarter(
  items: StockFinIndicatorRow[],
  market?: MarketCode | string | null,
): StockFinIndicatorRow[] {
  const byQuarter = new Map<number, StockFinIndicatorRow>();
  for (const row of items) {
    const meta = revenueComparablePeriod(row, market);
    if (!meta) continue;
    const index = quarterToIndex(meta.fiscalYear, meta.quarter);
    const existing = byQuarter.get(index);
    byQuarter.set(index, existing ? preferFinRow(existing, row) : row);
  }

  const byFingerprint = new Map<string, StockFinIndicatorRow[]>();
  const withoutFingerprint: StockFinIndicatorRow[] = [];
  for (const row of byQuarter.values()) {
    const fingerprint = metricFingerprint(row);
    if (!fingerprint) {
      withoutFingerprint.push(row);
      continue;
    }
    const group = byFingerprint.get(fingerprint) ?? [];
    group.push(row);
    byFingerprint.set(fingerprint, group);
  }

  const result: StockFinIndicatorRow[] = [...withoutFingerprint];
  for (const group of byFingerprint.values()) {
    if (group.length === 1) {
      result.push(group[0]);
      continue;
    }
    // Identical metrics under two labels: collapse only when cross-labeling is suspected.
    if (group.some(isCrossLabeledSuspect)) {
      result.push(group.reduce((best, row) => preferFinRow(best, row)));
      continue;
    }
    result.push(...group);
  }

  return result;
}

export function mapFinIndicatorsToFinancials(
  items: StockFinIndicatorRow[],
  market?: MarketCode | string | null,
): EntityFinancialYear[] {
  const normalizedMarket = market?.toLowerCase?.() ?? market;
  // Drop IPO / vendor duplicate periods before HK de-accumulation so dirty std
  // dates do not poison previous-period lookups.
  const deduped = dedupeFinRowsByComparableQuarter(items, market);
  // HK accumulate rows are de-accumulated here only (API returns raw cumulative data).
  const sourceItems =
    normalizedMarket === 'hk' ? deaccumulateHkFinRows(deduped) : deduped;
  const sorted = sortFinRows(sourceItems, market);
  const yoyByLabel = computeSameQuarterRevenueYoY(sorted, market);
  const slice = filterRowsForRevenueDisplay(sorted, market);

  return slice.map((row) => {
    const label = periodLabel(row);
    const axisLabel = unifiedFinPeriodAxisLabel(row, market);
    return {
      year: axisLabel,
      reportDate: extractDisclosureDate(row) || extractReportDate(row),
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
  const sorted = [...sortFinRows(quarterlyRows, market)].reverse();
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
