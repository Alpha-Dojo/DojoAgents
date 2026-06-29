import { useTranslation } from '../../hooks/useTranslation';
import type { MarketCode } from '../../types/dojoMesh';
import type { SectorPerformanceResponse } from '../../types/dojoSphere';
import { MARKET_CODE, MARKET_FLAG_IMAGE } from '../../utils/marketDisplay';
import { LoadingIndicator } from '../ui/LoadingIndicator';

interface SphereLevelRiskMetricsProps {
  performance: SectorPerformanceResponse | null | undefined;
  loading: boolean;
}

const MARKETS: MarketCode[] = ['us', 'cn', 'hk'];

type MetricKey =
  | 'cumulative_return_pct'
  | 'volatility_pct'
  | 'sharpe_ratio'
  | 'max_drawdown_pct'
  | 'calmar_ratio';

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
    labelKey: 'sphere.metricCumulativeReturn',
    format: (value) => formatPercent(value),
    tone: (value) => (value == null || value === 0 ? 'neutral' : value > 0 ? 'pos' : 'neg'),
  },
  {
    key: 'volatility_pct',
    labelKey: 'sphere.metricVolatility',
    format: (value) => formatPercent(value),
  },
  {
    key: 'sharpe_ratio',
    labelKey: 'sphere.metricSharpe',
    format: formatRatio,
    tone: (value) => (value == null || value === 0 ? 'neutral' : value > 0 ? 'pos' : 'neg'),
  },
  {
    key: 'calmar_ratio',
    labelKey: 'sphere.metricCalmar',
    format: formatRatio,
    tone: (value) => (value == null || value === 0 ? 'neutral' : value > 0 ? 'pos' : 'neg'),
  },
  {
    key: 'max_drawdown_pct',
    labelKey: 'sphere.metricMaxDrawdown',
    format: (value) => formatPercent(value),
    tone: () => 'neg',
  },
];

export function SphereLevelRiskMetrics({ performance, loading }: SphereLevelRiskMetricsProps) {
  const { t } = useTranslation();
  const hasStats = MARKETS.some((market) => performance?.stats_by_market?.[market] != null);

  return (
    <section className="sphere-level-risk" aria-busy={loading}>
      <h4 className="sphere-level-risk__title">{t('sphere.riskReturnMetrics')}</h4>

      {loading && !hasStats ? (
        <LoadingIndicator
          className="sphere-level-risk__status"
          label={t('sphere.loadingPerformance')}
          variant="panel"
        />
      ) : !hasStats ? (
        <p className="sphere-level-risk__status">{t('sphere.noPerformanceData')}</p>
      ) : (
        <table className="sphere-level-risk__table">
          <thead>
            <tr>
              <th scope="col" className="sphere-level-risk__corner" aria-hidden />
              {METRIC_COLUMNS.map((column) => (
                <th key={column.key} scope="col" className="sphere-level-risk__metric-head">
                  {t(column.labelKey)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {MARKETS.map((market) => (
              <tr key={market}>
                <th scope="row" className={`sphere-level-risk__market-row sphere-level-risk__market-row--${market}`}>
                  <span className="sphere-level-risk__market-label">
                    <img className="sphere-level-risk__market-flag" src={MARKET_FLAG_IMAGE[market]} alt="" aria-hidden />
                    <span className="sphere-level-risk__market-code">{MARKET_CODE[market]}</span>
                  </span>
                </th>
                {METRIC_COLUMNS.map((column) => {
                  const value = performance?.stats_by_market?.[market]?.[column.key];
                  const tone = column.tone?.(value) ?? 'neutral';
                  return (
                    <td
                      key={column.key}
                      className={`sphere-level-risk__value sphere-level-risk__value--${tone}`}
                    >
                      {column.format(value)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
