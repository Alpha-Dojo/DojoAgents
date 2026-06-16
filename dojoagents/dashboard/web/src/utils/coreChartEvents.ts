import type { CoreChartEvent, CoreKlineBar, StockFinIndicatorRow } from '../types/dojoCore';
import { extractReportDate } from './coreFinIndicators';
import { findClosestDateIndex, normalizeChartDates } from './coreChartLink';
import { candleSlot } from './coreCharts';

/** Supported K-line event kinds — extend with new types and CSS modifiers. */
export type CoreChartEventKind = CoreChartEvent['kind'];

const MARKER_BADGE_HALF_W = 2.4;
const MARKER_BADGE_H = 4.5;
const MARKER_STEM_H = 3;

/** Standard fiscal quarter-end dates used for earnings markers. */
const QUARTER_END_SUFFIXES = new Set(['03-31', '06-30', '09-30', '12-31']);

const QUARTER_CODE_BY_SUFFIX: Record<string, string> = {
  '03-31': 'Q1',
  '06-30': 'Q2',
  '09-30': 'Q3',
  '12-31': 'Q4',
};

/** SVG shapes for a compact diamond pin at the top of the plot. */
export function eventMarkerPaths(
  cx: number,
  topY: number,
): {
  diamond: string;
  stemTop: number;
  stemBottom: number;
  hitX: number;
  hitY: number;
  hitW: number;
  hitH: number;
} {
  const y0 = topY;
  const badgeBottom = y0 + MARKER_BADGE_H;
  const diamond = [
    `M ${cx} ${y0}`,
    `L ${cx + MARKER_BADGE_HALF_W} ${y0 + MARKER_BADGE_H / 2}`,
    `L ${cx} ${badgeBottom}`,
    `L ${cx - MARKER_BADGE_HALF_W} ${y0 + MARKER_BADGE_H / 2}`,
    'Z',
  ].join(' ');
  const stemBottom = badgeBottom + MARKER_STEM_H;
  return {
    diamond,
    stemTop: badgeBottom,
    stemBottom,
    hitX: cx - 5,
    hitY: y0 - 1,
    hitW: 10,
    hitH: MARKER_BADGE_H + MARKER_STEM_H + 2,
  };
}

function isStandardQuarterEnd(reportDate: string): boolean {
  return QUARTER_END_SUFFIXES.has(reportDate.slice(5, 10));
}

/** First bar on/after ``targetDate``; falls back to closest bar. */
export function findBarIndexOnOrAfter(dates: string[], targetDate: string): number {
  if (!targetDate || dates.length === 0) return -1;

  const target = targetDate.slice(0, 10);
  const exact = dates.findIndex((day) => day === target);
  if (exact >= 0) return exact;

  for (let i = 0; i < dates.length; i += 1) {
    if (dates[i] >= target) return i;
  }

  return findClosestDateIndex(dates, target);
}

export function buildEarningsEventsFromFinIndicators(
  items: StockFinIndicatorRow[],
): CoreChartEvent[] {
  const seen = new Set<string>();
  const events: CoreChartEvent[] = [];

  for (const row of items) {
    const reportDate = extractReportDate(row);
    if (!reportDate || reportDate.length < 10 || seen.has(reportDate)) continue;
    if (!isStandardQuarterEnd(reportDate)) continue;
    seen.add(reportDate);

    const label = row.report_period_name?.trim() || reportDate;
    const quarterCode = QUARTER_CODE_BY_SUFFIX[reportDate.slice(5, 10)] ?? '';
    events.push({
      id: `earnings-${reportDate}`,
      kind: 'earnings',
      date: reportDate,
      label,
      quarterCode,
    });
  }

  return events.sort((a, b) => a.date.localeCompare(b.date));
}

export interface CoreChartEventMarker {
  event: CoreChartEvent;
  visibleIndex: number;
  cx: number;
}

export function mapEventsToVisibleMarkers(
  events: CoreChartEvent[],
  visibleBars: CoreKlineBar[],
  visibleStartIndex: number,
  allBars: CoreKlineBar[],
  plotW: number,
  plotX0: number,
): CoreChartEventMarker[] {
  if (!events.length || !visibleBars.length || !allBars.length || plotW <= 0) return [];

  const allDates = normalizeChartDates(allBars);
  const windowStart = allDates[visibleStartIndex] ?? '';
  const windowEnd = allDates[visibleStartIndex + visibleBars.length - 1] ?? '';
  const markers: CoreChartEventMarker[] = [];
  const usedVisibleIndices = new Set<number>();

  for (const event of events) {
    if (windowStart && event.date < windowStart) continue;
    if (windowEnd && event.date > windowEnd) continue;

    const globalIndex = findBarIndexOnOrAfter(allDates, event.date);
    if (globalIndex < 0) continue;

    const visibleIndex = globalIndex - visibleStartIndex;
    if (visibleIndex < 0 || visibleIndex >= visibleBars.length) continue;
    if (usedVisibleIndices.has(visibleIndex)) continue;
    usedVisibleIndices.add(visibleIndex);

    const { cx } = candleSlot(visibleIndex, visibleBars.length, plotW, plotX0);
    markers.push({ event, visibleIndex, cx });
  }

  return markers;
}
