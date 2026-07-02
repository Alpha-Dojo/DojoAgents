import type { MarketCode } from '../types/market';
import type {
  EntityFinancialYear,
  EntityProfitabilityAxis,
  StockFinIndicatorRow,
} from '../types/entity';

export const REVENUE_CHART_YOY_BASELINE_START = '2022-01-01';
export const REVENUE_CHART_DISPLAY_FROM_YEAR = 2024;

/** When disclosure follows std_report_date within this window, fiscal quarter already aligns with natural calendar. */
const SHORT_DISCLOSURE_LAG_DAYS = 45;
/** Typical calendar-quarter length for inferring fiscal→natural shift from disclosure lag. */
const CALENDAR_QUARTER_DAYS = 90;

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

/** Disclosure / filing date (report_date only; not fiscal period-end). */
export function extractDisclosureDate(row: StockFinIndicatorRow): string {
  const raw = row.report_date || '';
  const text = String(raw).trim();
  if (!text) return '';
  if (text.includes('T')) return text.split('T', 1)[0] ?? text;
  if (text.includes(' ')) return text.split(' ', 1)[0] ?? text;
  return text.slice(0, 10);
}

/** Unified revenue-chart axis label: natural-calendar quarter (fiscal period + series offset). */
export function unifiedFinPeriodAxisLabel(
  row: StockFinIndicatorRow,
  market?: MarketCode | string | null,
  seriesOffset?: number,
): string {
  const meta = naturalCalendarPeriod(row, market, seriesOffset);
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
  market?: MarketCode | string | null,
  seriesOffset?: number,
): CalendarPeriod | null {
  return naturalCalendarPeriod(row, market, seriesOffset);
}

function sortFinRows(
  items: StockFinIndicatorRow[],
  market?: MarketCode | string | null,
  seriesOffset?: number,
): StockFinIndicatorRow[] {
  return [...items].sort((a, b) => {
    const ma = revenueComparablePeriod(a, market, seriesOffset);
    const mb = revenueComparablePeriod(b, market, seriesOffset);
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

/** Fiscal period-end date when present (not used for natural-calendar axis). */
function extractStdReportDate(row: StockFinIndicatorRow): string {
  const raw = row.std_report_date || '';
  const text = String(raw).trim();
  if (!text) return '';
  if (text.includes('T')) return text.split('T', 1)[0] ?? text;
  if (text.includes(' ')) return text.split(' ', 1)[0] ?? text;
  return text.slice(0, 10);
}

type CalendarPeriod = { fiscalYear: string; quarter: ComparableQuarter };

const CALENDAR_QUARTER_BY_MONTH_INDEX: ComparableQuarter[] = ['q1', 'q2', 'q3', 'q4'];

/** Natural-calendar quarter from any ISO date (month-based; supports non month-end disclosure). */
function calendarQuarterFromIsoDate(date: string): CalendarPeriod | null {
  if (date.length < 7) return null;
  const year = date.slice(0, 4);
  const month = Number(date.slice(5, 7));
  if (!Number.isFinite(month) || month < 1 || month > 12) return null;
  const quarter = CALENDAR_QUARTER_BY_MONTH_INDEX[Math.floor((month - 1) / 3)];
  return { fiscalYear: year, quarter };
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

function disclosureMinusFiscalQuarterOffset(
  row: StockFinIndicatorRow,
  fiscal: CalendarPeriod,
): number {
  const natural = calendarQuarterFromIsoDate(extractDisclosureDate(row));
  if (!natural) return 0;
  return (
    quarterToIndex(natural.fiscalYear, natural.quarter) -
    quarterToIndex(fiscal.fiscalYear, fiscal.quarter)
  );
}

/**
 * Per-row gap from fiscal quarter (report_period_name) to natural calendar quarter.
 * Short post-period disclosure (NVDA): 0. Long lag (BABA/HK/SNDK): ~ceil(lag / quarter).
 * Pre-period disclosure (AAPL): disclosure quarter gap (typically -1).
 */
function detectFiscalToNaturalOffset(row: StockFinIndicatorRow): number {
  const fiscal = fiscalPeriodFromReport(row);
  if (!fiscal) return 0;

  const disclosure = extractDisclosureDate(row);
  const stdDate = extractStdReportDate(row);

  if (disclosure && stdDate && disclosure < stdDate) {
    return disclosureMinusFiscalQuarterOffset(row, fiscal);
  }

  const lagDays = stdDate && disclosure ? daysBetweenIsoDates(stdDate, disclosure) : null;
  if (lagDays != null && lagDays >= 0 && lagDays <= SHORT_DISCLOSURE_LAG_DAYS) {
    return 0;
  }

  if (lagDays != null && lagDays > SHORT_DISCLOSURE_LAG_DAYS) {
    return Math.max(1, Math.round(lagDays / CALENDAR_QUARTER_DAYS));
  }

  return disclosureMinusFiscalQuarterOffset(row, fiscal);
}

/** Series-level fiscal→natural offset: mode of per-row gaps across fin history. */
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
 * Natural-calendar quarter for chart axis / YoY / filtering.
 * Primary: fiscal report_period_name shifted by series-level fiscal→natural offset.
 * Fallback: std_report_date or disclosure date calendar quarter.
 */
function naturalCalendarPeriod(
  row: StockFinIndicatorRow,
  _market?: MarketCode | string | null,
  seriesOffset?: number,
): CalendarPeriod | null {
  const fiscal = fiscalPeriodFromReport(row);
  if (fiscal) {
    const offset =
      seriesOffset !== undefined ? seriesOffset : detectFiscalToNaturalOffset(row);
    return shiftCalendarPeriod(fiscal, offset);
  }

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

function indexToQuarter(index: number): CalendarPeriod {
  const quarters: ComparableQuarter[] = ['q1', 'q2', 'q3', 'q4'];
  const normalized = ((index % 4) + 4) % 4;
  const year = Math.floor(index / 4);
  return { fiscalYear: String(year), quarter: quarters[normalized] };
}

function shiftCalendarPeriod(base: CalendarPeriod, quarterOffset: number): CalendarPeriod {
  return indexToQuarter(quarterToIndex(base.fiscalYear, base.quarter) + quarterOffset);
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
  market?: MarketCode | string | null,
  seriesOffset?: number,
): CalendarPeriod | null {
  return naturalCalendarPeriod(row, market, seriesOffset);
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
  seriesOffset?: number,
): Map<string, number | null> {
  const normalizedMarket = market?.toLowerCase?.() ?? market;
  const filterCumulativeLike = normalizedMarket === 'hk';

  const peerRevenues: number[] = [];
  for (const row of rows) {
    const revenue = row.total_operating_revenue;
    if (revenue != null && !Number.isNaN(revenue) && revenue > 0) {
      peerRevenues.push(revenue);
    }
  }

  const revenueByQuarter = new Map<string, number>();
  for (const row of rows) {
    const meta = revenueComparablePeriod(row, market, seriesOffset);
    if (!meta) continue;
    const revenue = row.total_operating_revenue;
    if (revenue == null || Number.isNaN(revenue)) continue;
    if (filterCumulativeLike && looksLikeHkCumulativeQuarterRevenue(revenue, peerRevenues)) continue;
    revenueByQuarter.set(`${meta.fiscalYear}:${meta.quarter}`, revenue);
  }

  const yoyByLabel = new Map<string, number | null>();
  for (const row of rows) {
    const label = periodLabel(row);
    const meta = revenueComparablePeriod(row, market, seriesOffset);
    if (!meta) {
      yoyByLabel.set(label, null);
      continue;
    }

    const prevYear = String(Number(meta.fiscalYear) - 1);
    const prevRevenue = revenueByQuarter.get(`${prevYear}:${meta.quarter}`);
    const currentRevenue = row.total_operating_revenue;
    if (
      prevRevenue == null ||
      prevRevenue === 0 ||
      currentRevenue == null ||
      (filterCumulativeLike &&
        looksLikeHkCumulativeQuarterRevenue(currentRevenue, peerRevenues))
    ) {
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

function looksLikeHkCumulativeQuarterRevenue(revenue: number, peerRevenues: number[]): boolean {
  if (peerRevenues.length === 0) return false;
  const sorted = [...peerRevenues].sort((a, b) => a - b);
  const median = sorted[Math.floor(sorted.length / 2)];
  return median > 0 && revenue > median * 2.5;
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
  seriesOffset?: number,
): StockFinIndicatorRow[] {
  const minIndex = quarterToIndex(String(REVENUE_CHART_DISPLAY_FROM_YEAR), REVENUE_CHART_DISPLAY_FROM_QUARTER);
  return rows.filter((row) => {
    if (!isDisclosedFinRow(row)) return false;
    const meta = revenueComparablePeriod(row, market, seriesOffset);
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
  const seriesOffset = resolveFiscalToNaturalOffset(sourceItems);
  const sorted = sortFinRows(sourceItems, market, seriesOffset);
  const yoyByLabel = computeSameQuarterRevenueYoY(sorted, market, seriesOffset);
  const slice = filterRowsForRevenueDisplay(sorted, market, seriesOffset);

  return slice.map((row) => {
    const label = periodLabel(row);
    const axisLabel = unifiedFinPeriodAxisLabel(row, market, seriesOffset);
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
  const seriesOffset = resolveFiscalToNaturalOffset(rows);
  const quarterlyRows = rows.filter(
    (row) => calendarPeriodFromRow(row, market, seriesOffset) != null,
  );
  const sorted = [...sortFinRows(quarterlyRows, market, seriesOffset)].reverse();
  const seen = new Set<number>();
  let sum = 0;
  let count = 0;
  for (const row of sorted) {
    const period = calendarPeriodFromRow(row, market, seriesOffset);
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
