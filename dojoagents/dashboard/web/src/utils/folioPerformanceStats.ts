import type { FolioPerformanceStats, FolioPerformanceView } from '../types/dojoFolio';
import type { MarketCode } from '../types/dojoMesh';

const TRADING_DAYS_YEAR = 252;
const MARKETS: MarketCode[] = ['us', 'cn', 'hk'];

function mean(values: number[]): number {
  if (values.length === 0) return 0;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function stdev(values: number[]): number {
  if (values.length < 2) return 0;
  const avg = mean(values);
  const variance =
    values.reduce((sum, value) => sum + (value - avg) ** 2, 0) / (values.length - 1);
  return Math.sqrt(variance);
}

export function computePerformanceStats(
  series: Array<{ date: string; value: number }>,
): FolioPerformanceStats | null {
  if (series.length < 2) return null;

  const values = series.filter((point) => point.date && Number.isFinite(point.value));
  if (values.length < 2) return null;

  const firstValue = values[0].value;
  const lastValue = values[values.length - 1].value;
  if (firstValue <= 0) return null;

  const cumulativeReturnPct = Number(((lastValue / firstValue - 1) * 100).toFixed(2));

  const dailyReturns: number[] = [];
  for (let index = 1; index < values.length; index += 1) {
    const prev = values[index - 1].value;
    const curr = values[index].value;
    if (prev > 0) dailyReturns.push(curr / prev - 1);
  }

  let sharpeRatio: number | null = null;
  let volatilityPct: number | null = null;
  if (dailyReturns.length >= 2) {
    const meanReturn = mean(dailyReturns);
    const stdReturn = stdev(dailyReturns);
    if (stdReturn > 0) {
      sharpeRatio = Number(((meanReturn / stdReturn) * Math.sqrt(TRADING_DAYS_YEAR)).toFixed(2));
      volatilityPct = Number((stdReturn * Math.sqrt(TRADING_DAYS_YEAR) * 100).toFixed(2));
    } else {
      volatilityPct = 0;
    }
  }

  let peak = firstValue;
  let maxDrawdownPct = 0;
  for (const point of values) {
    if (point.value > peak) peak = point.value;
    if (peak > 0) {
      const drawdown = ((point.value - peak) / peak) * 100;
      if (drawdown < maxDrawdownPct) maxDrawdownPct = drawdown;
    }
  }
  maxDrawdownPct = Number(maxDrawdownPct.toFixed(2));

  let calmarRatio: number | null = null;
  const tradingDays = values.length;
  if (tradingDays > 0 && maxDrawdownPct < 0) {
    const totalReturn = lastValue / firstValue;
    const annualizedReturn = totalReturn ** (TRADING_DAYS_YEAR / tradingDays) - 1;
    calmarRatio = Number((annualizedReturn / Math.abs(maxDrawdownPct / 100)).toFixed(2));
  }

  return {
    cumulative_return_pct: cumulativeReturnPct,
    volatility_pct: volatilityPct,
    sharpe_ratio: sharpeRatio,
    calmar_ratio: calmarRatio,
    max_drawdown_pct: maxDrawdownPct,
    trading_days: tradingDays,
  };
}

export function pickBenchmarkSeriesForSymbol(
  performance: FolioPerformanceView,
  benchmarkSymbol?: string | null,
): Array<{ date: string; value: number }> {
  if (benchmarkSymbol) {
    for (const market of MARKETS) {
      const symbol = performance.benchmarkSymbolByMarket[market];
      const series = performance.benchmarkByMarket[market];
      if (symbol === benchmarkSymbol && series?.length) {
        return series;
      }
    }
  }

  let best: Array<{ date: string; value: number }> = [];
  for (const market of MARKETS) {
    const series = performance.benchmarkByMarket[market];
    if (series && series.length > best.length) {
      best = series;
    }
  }
  return best;
}

export function resolveBenchmarkStats(
  performance: FolioPerformanceView | null | undefined,
  benchmarkSymbol?: string | null,
): FolioPerformanceStats | null {
  if (!performance) return null;
  const series = pickBenchmarkSeriesForSymbol(performance, benchmarkSymbol);
  return computePerformanceStats(series);
}
