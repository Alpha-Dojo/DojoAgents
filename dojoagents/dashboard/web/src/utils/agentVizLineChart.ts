import { buildLinePath } from './folioFormat';
import { formatSignedPercent, priceTickValues } from './coreCharts';
import {
  buildIndependentMarketPath,
  valueToChartY,
  type MarketSeriesPoint,
} from './spherePerformanceSeries';
import { agentMarketLineColor, isBenchmarkSeries, normalizeAgentMarket } from './agentVizMarket';
import type { AgentVizLineSeries } from '../types/agentViz';

export interface PreparedLinePoint {
  date: string;
  value: number;
}

export interface PreparedLineSeries {
  id: string;
  label: string;
  market: string | null;
  dashed: boolean;
  points: PreparedLinePoint[];
  path: string;
  color: string;
}

function coerceValue(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return null;
}

function rebasePoints(points: PreparedLinePoint[]): PreparedLinePoint[] {
  if (points.length === 0) return [];
  const base = points[0].value;
  if (base <= 0) return points;
  return points.map((point) => ({
    date: point.date,
    value: Number(((point.value / base) * 100).toFixed(4)),
  }));
}

function isIndexedSeries(points: PreparedLinePoint[]): boolean {
  if (points.length < 2) return false;
  const first = points[0].value;
  if (first < 80 || first > 120) return false;
  return points.every((point) => point.value > 0 && point.value < 5000);
}

function normalizeSeries(raw: AgentVizLineSeries): PreparedLinePoint[] {
  return (raw.points ?? [])
    .map((point, index) => {
      const value = coerceValue(point.value);
      if (value === null) return null;
      const date = typeof point.date === 'string' && point.date ? point.date : `#${index}`;
      return { date, value };
    })
    .filter((point): point is PreparedLinePoint => point !== null);
}

function seriesColor(series: AgentVizLineSeries, index: number, dashed: boolean): string {
  if (dashed || isBenchmarkSeries(series.id)) {
    const market = normalizeAgentMarket(series.market) ?? normalizeAgentMarket(series.id.replace(/^bench_/, ''));
    return market ? `${agentMarketLineColor(market)}66` : '#78909c88';
  }
  return agentMarketLineColor(series.market ?? series.id, index);
}

function yBounds(values: number[]): { yMin: number; yMax: number } {
  const rawMin = Math.min(...values);
  const rawMax = Math.max(...values);
  const span = rawMax - rawMin || Math.max(Math.abs(rawMax), 1) * 0.05;
  const pad = span * 0.08;
  return { yMin: rawMin - pad, yMax: rawMax + pad };
}

export function prepareAgentLineChart(
  series: AgentVizLineSeries[],
  benchmark: AgentVizLineSeries[],
  width: number,
  height: number,
  options: { includeBenchmarks?: boolean; independentScale?: boolean; skipRebase?: boolean } = {},
): PreparedLineSeries[] {
  const includeBenchmarks = options.includeBenchmarks ?? false;
  const independentScale = options.independentScale ?? false;
  const skipRebase = options.skipRebase ?? false;

  const navSeries = series
    .map((raw) => {
      const normalized = normalizeSeries(raw);
      const points =
        skipRebase || isIndexedSeries(normalized) ? normalized : rebasePoints(normalized);
      return { raw, points };
    })
    .filter((entry) => entry.points.length >= 2);

  const benchSeries = includeBenchmarks
    ? benchmark
        .map((raw) => {
          const normalized = normalizeSeries(raw);
          const points = skipRebase || isIndexedSeries(normalized) ? normalized : rebasePoints(normalized);
          return { raw, points };
        })
        .filter((entry) => entry.points.length >= 2)
    : [];

  const allEntries = [...navSeries, ...benchSeries];
  if (allEntries.length === 0) return [];

  const globalValues = allEntries.flatMap((entry) => entry.points.map((point) => point.value));
  const globalBounds = yBounds(globalValues);

  return allEntries
    .map(({ raw, points }, index) => {
      const dashed = Boolean(raw.dashed) || isBenchmarkSeries(raw.id);
      const values = points.map((point) => point.value);
      const bounds = independentScale ? yBounds(values) : globalBounds;
      const path = buildLinePath(values, width, height, bounds.yMin, bounds.yMax);
      return {
        id: raw.id,
        label: raw.label,
        market: normalizeAgentMarket(raw.market ?? raw.id),
        dashed,
        points,
        path,
        color: seriesColor(raw, index, dashed),
      };
    })
    .filter((entry) => entry.path.length > 0);
}

export interface AgentPortfolioNavLayer {
  id: string;
  label: string;
  market: ReturnType<typeof normalizeAgentMarket>;
  color: string;
  path: string;
  points: MarketSeriesPoint[];
}

export interface AgentPortfolioNavChart {
  yMin: number;
  yMax: number;
  layers: AgentPortfolioNavLayer[];
}

/** Same shared-axis multi-line logic as DojoFolio NAV curve (indexed values, no rebase). */
export function prepareAgentPortfolioNavChart(
  series: AgentVizLineSeries[],
  width: number,
  height: number,
  padX = 6,
  padY = 6,
): AgentPortfolioNavChart | null {
  const layers = series
    .map((raw) => {
      const points: MarketSeriesPoint[] = (raw.points ?? [])
        .map((point, index) => {
          const value = coerceValue(point.value);
          if (value === null) return null;
          const date =
            typeof point.date === 'string' && point.date ? point.date : `#${index}`;
          return { date, value };
        })
        .filter((point): point is MarketSeriesPoint => point !== null);
      if (points.length < 2) return null;
      const market = normalizeAgentMarket(raw.market ?? raw.id);
      return {
        id: raw.id,
        label: raw.label,
        market,
        points,
      };
    })
    .filter((layer): layer is NonNullable<typeof layer> => layer !== null);

  if (!layers.length) return null;

  const values = layers.flatMap((layer) => layer.points.map((point) => point.value));
  const dataMin = Math.min(...values);
  const dataMax = Math.max(...values);
  const span = dataMax - dataMin || 1;
  const pad = Math.max(span * 0.08, 1.5);
  const yMin = dataMin - pad;
  const yMax = dataMax + pad;

  return {
    yMin,
    yMax,
    layers: layers.map((layer) => ({
      id: layer.id,
      label: layer.label,
      market: layer.market,
      color: agentMarketLineColor(layer.market ?? layer.id),
      points: layer.points,
      path: buildIndependentMarketPath(
        layer.points,
        width,
        height,
        yMin,
        yMax,
        padX,
        padY,
      ),
    })).filter((layer) => layer.path.length > 0),
  };
}

export function buildAgentNavReturnAxisTicks(
  yMin: number,
  yMax: number,
  height: number,
  padY = 6,
  count = 4,
): Array<{ indexValue: number; label: string; y: number; topPct: number }> {
  const pctMin = yMin - 100;
  const pctMax = yMax - 100;
  const span = Math.abs(pctMax - pctMin);
  const digits = span <= 15 ? 1 : 0;

  return priceTickValues(pctMin, pctMax, count).map((pct) => {
    const indexValue = pct + 100;
    const y = valueToChartY(indexValue, yMin, yMax, height, padY);
    return {
      indexValue,
      label: formatSignedPercent(pct, digits),
      y,
      topPct: (y / height) * 100,
    };
  });
}
