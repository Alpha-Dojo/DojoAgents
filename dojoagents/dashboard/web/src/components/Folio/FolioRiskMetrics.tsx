import { useMemo } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import type { FolioPerformanceStats, FolioPerformanceView } from '../../types/folio';
import type { MarketCode } from '../../types/market';
import { resolveBenchmarkStats } from '../../utils/folioPerformanceStats';
import { MARKET_CODE, MARKET_FLAG } from '../../utils/marketDisplay';

interface FolioRiskMetricsProps {
  performance: FolioPerformanceView | null | undefined;
  loading?: boolean;
  benchmarkSymbol?: string | null;
  benchmarkLabel?: string | null;
}

const MARKETS: MarketCode[] = ['us', 'cn', 'hk'];

type MetricKey =
  | 'cumulative_return_pct'
  | 'volatility_pct'
  | 'sharpe_ratio'
  | 'calmar_ratio'
  | 'max_drawdown_pct';

interface MetricColumn {
  key: MetricKey;
  labelKey: string;
  format: (value: number | null | undefined) => string;
  tone?: (value: number | null | undefined) => 'pos' | 'neg' | 'neutral';
}

function formatPercent(value: number | null | undefined, digits = 2): string {
  if (value == null || Number.isNaN(value)) return '—';
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toFixed(digits)}%`;
}

function formatRatio(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—';
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toFixed(2)}`;
}

const METRIC_COLUMNS: MetricColumn[] = [
  {
    key: 'cumulative_return_pct',
    labelKey: 'sectorPage.metricCumulativeReturn',
    format: (value) => formatPercent(value),
    tone: (value) => (value == null || value === 0 ? 'neutral' : value > 0 ? 'pos' : 'neg'),
  },
  {
    key: 'volatility_pct',
    labelKey: 'sectorPage.metricVolatility',
    format: (value) => formatPercent(value),
  },
  {
    key: 'sharpe_ratio',
    labelKey: 'sectorPage.metricSharpe',
    format: formatRatio,
    tone: (value) => (value == null || value === 0 ? 'neutral' : value > 0 ? 'pos' : 'neg'),
  },
  {
    key: 'calmar_ratio',
    labelKey: 'sectorPage.metricCalmar',
    format: formatRatio,
    tone: (value) => (value == null || value === 0 ? 'neutral' : value > 0 ? 'pos' : 'neg'),
  },
  {
    key: 'max_drawdown_pct',
    labelKey: 'sectorPage.metricMaxDrawdown',
    format: (value) => formatPercent(value),
    tone: () => 'neg',
  },
];

function renderMetricCells(stats: FolioPerformanceStats) {
  return METRIC_COLUMNS.map((column) => {
    const value = stats[column.key];
    const tone = column.tone?.(value) ?? 'neutral';
    return (
      <td key={column.key} className={`folio-risk__value folio-risk__value--${tone}`}>
        {column.format(value)}
      </td>
    );
  });
}

export function FolioRiskMetrics({
  performance,
  loading = false,
  benchmarkSymbol = null,
  benchmarkLabel = null,
}: FolioRiskMetricsProps) {
  const { t } = useTranslation();
  const hasStats = MARKETS.some((market) => performance?.statsByMarket?.[market] != null);
  const benchmarkStats = useMemo(
    () => resolveBenchmarkStats(performance, benchmarkSymbol),
    [benchmarkSymbol, performance],
  );

  const benchmarkRowLabel = benchmarkLabel?.trim() || benchmarkSymbol || t('sectorPage.benchmarkLabel');

  return (
    <section className="folio-risk" aria-busy={loading}>
      <h4 className="folio-risk__title">{t('sectorPage.riskReturnMetrics')}</h4>

      {loading && !hasStats ? (
        <p className="folio-risk__status">{t('folio.loading')}</p>
      ) : !hasStats ? (
        <p className="folio-risk__status">{t('folio.noPerformanceData')}</p>
      ) : (
        <table className="folio-risk__table">
          <thead>
            <tr>
              <th scope="col" className="folio-risk__corner" aria-hidden />
              {METRIC_COLUMNS.map((column) => (
                <th key={column.key} scope="col" className="folio-risk__metric-head">
                  {t(column.labelKey)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {MARKETS.map((market) => {
              const stats = performance?.statsByMarket?.[market];
              if (!stats) return null;
              return (
                <tr key={market}>
                  <th scope="row" className={`folio-risk__market-row folio-risk__market-row--${market}`}>
                    <span className="folio-risk__market-label">
                      <span className="folio-risk__market-flag" aria-hidden>
                        {MARKET_FLAG[market]}
                      </span>
                      <span className="folio-risk__market-code">{MARKET_CODE[market]}</span>
                    </span>
                  </th>
                  {renderMetricCells(stats)}
                </tr>
              );
            })}
            {benchmarkStats ? (
              <tr className="folio-risk__benchmark-row">
                <th scope="row" className="folio-risk__market-row folio-risk__market-row--benchmark">
                  <span className="folio-risk__benchmark-label" title={benchmarkRowLabel}>
                    {benchmarkRowLabel}
                  </span>
                </th>
                {renderMetricCells(benchmarkStats)}
              </tr>
            ) : null}
          </tbody>
        </table>
      )}
    </section>
  );
}
