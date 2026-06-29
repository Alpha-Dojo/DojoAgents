import type { EntityIncomeDistributionItem, EntityIncomeMainopType } from '../types/entity';

export const INCOME_MAINOP_TYPES: EntityIncomeMainopType[] = ['1', '2', '3'];

export const INCOME_SLICE_COLORS = [
  '#00e5ff',
  '#00e676',
  '#ff9800',
  '#5c6bc0',
  '#26c6da',
  '#ab47bc',
  '#78909c',
] as const;

const MAX_VISIBLE_SLICES = 5;

const AGGREGATE_ITEM_NAMES = new Set(['总计', '合计']);

export function isAggregateIncomeItem(name: string): boolean {
  return AGGREGATE_ITEM_NAMES.has(name.trim());
}

export interface IncomeChartSlice {
  key: string;
  name: string;
  value: number;
  color: string;
  ratio: number;
  isOthers?: boolean;
}

export function formatReportDateLabel(reportDate: string | null | undefined): string | null {
  if (!reportDate) return null;
  const match = reportDate.match(/^(\d{4}-\d{2}-\d{2})/);
  return match ? match[1] : reportDate;
}

export function prepareIncomeListRows(items: EntityIncomeDistributionItem[]): IncomeChartSlice[] {
  const sorted = [...items]
    .filter((item) => item.main_business_income > 0 && !isAggregateIncomeItem(item.item_name))
    .sort((a, b) => b.main_business_income - a.main_business_income);

  if (!sorted.length) return [];

  const total = sorted.reduce((sum, item) => sum + item.main_business_income, 0);
  if (total <= 0) return [];

  return sorted.map((item, index) => ({
    key: `${item.item_name}:${index}`,
    name: item.item_name,
    value: item.main_business_income,
    color: INCOME_SLICE_COLORS[index % INCOME_SLICE_COLORS.length],
    ratio: item.main_business_income / total,
  }));
}

export function prepareIncomeChartSlices(
  items: EntityIncomeDistributionItem[],
  othersLabel: string,
): IncomeChartSlice[] {
  const rows = prepareIncomeListRows(items);
  if (!rows.length) return [];

  if (rows.length <= MAX_VISIBLE_SLICES + 1) {
    return rows;
  }

  const top = rows.slice(0, MAX_VISIBLE_SLICES);
  const rest = rows.slice(MAX_VISIBLE_SLICES);
  const othersValue = rest.reduce((sum, item) => sum + item.value, 0);
  const total = rows.reduce((sum, item) => sum + item.value, 0);

  return [
    ...top,
    {
      key: `${othersLabel}:others`,
      name: othersLabel,
      value: othersValue,
      color: INCOME_SLICE_COLORS[MAX_VISIBLE_SLICES % INCOME_SLICE_COLORS.length],
      ratio: othersValue / total,
      isOthers: true,
    },
  ];
}

export function resolveHoveredDonutKey(
  listKey: string | null,
  donutSlices: IncomeChartSlice[],
): string | null {
  if (!listKey) return null;

  const direct = donutSlices.find((slice) => slice.key === listKey);
  if (direct) return direct.key;

  const others = donutSlices.find((slice) => slice.isOthers);
  if (!others) return null;

  const topKeys = new Set(donutSlices.filter((slice) => !slice.isOthers).map((slice) => slice.key));
  return topKeys.has(listKey) ? null : others.key;
}

export function isIncomeRowLinkedToDonutKey(
  rowKey: string,
  donutKey: string | null,
  donutSlices: IncomeChartSlice[],
): boolean {
  if (!donutKey) return false;
  if (rowKey === donutKey) return true;

  const slice = donutSlices.find((item) => item.key === donutKey);
  if (!slice?.isOthers) return false;

  const topKeys = new Set(donutSlices.filter((item) => !item.isOthers).map((item) => item.key));
  return !topKeys.has(rowKey);
}

export function describeDonutArc(
  cx: number,
  cy: number,
  outerR: number,
  innerR: number,
  startAngle: number,
  endAngle: number,
): string {
  if (endAngle - startAngle >= Math.PI * 2 - 1e-6) {
    endAngle = startAngle + Math.PI * 2 - 1e-6;
  }

  const largeArc = endAngle - startAngle > Math.PI ? 1 : 0;
  const x1 = cx + outerR * Math.cos(startAngle);
  const y1 = cy + outerR * Math.sin(startAngle);
  const x2 = cx + outerR * Math.cos(endAngle);
  const y2 = cy + outerR * Math.sin(endAngle);
  const x3 = cx + innerR * Math.cos(endAngle);
  const y3 = cy + innerR * Math.sin(endAngle);
  const x4 = cx + innerR * Math.cos(startAngle);
  const y4 = cy + innerR * Math.sin(startAngle);

  return [
    `M ${x1} ${y1}`,
    `A ${outerR} ${outerR} 0 ${largeArc} 1 ${x2} ${y2}`,
    `L ${x3} ${y3}`,
    `A ${innerR} ${innerR} 0 ${largeArc} 0 ${x4} ${y4}`,
    'Z',
  ].join(' ');
}

export function buildDonutPaths(
  slices: IncomeChartSlice[],
  cx: number,
  cy: number,
  outerR: number,
  innerR: number,
): Array<{ key: string; path: string; color: string; slice: IncomeChartSlice }> {
  if (!slices.length) return [];

  let angle = -Math.PI / 2;
  return slices.map((slice) => {
    const sweep = slice.ratio * Math.PI * 2;
    const start = angle;
    const end = angle + sweep;
    angle = end;
    return {
      key: slice.key,
      path: describeDonutArc(cx, cy, outerR, innerR, start, end),
      color: slice.color,
      slice,
    };
  });
}
