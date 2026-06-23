import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import type { FolioPortfolioDetail } from '../../api/dojoFolio';
import type { MarketCode } from '../../types/dojoMesh';
import type { FolioKpiMetric, FolioPortfolioConfig } from '../../types/dojoFolio';
import { DEFAULT_FOLIO_CONFIG, FOLIO_MARKETS } from '../../types/dojoFolio';
import { buildLinePath } from '../../utils/folioFormat';
import { formatMarketNetValue } from '../../utils/folioCompute';
import { FolioDetailTabs } from './FolioDetailTabs';
import { FolioMarketLabel } from './FolioMarketLabel';
import { FolioStartDatePicker } from './FolioStartDatePicker';

interface FolioOverviewPanelProps {
  portfolio: FolioPortfolioDetail;
  loading?: boolean;
  addingTicker?: boolean;
  removingTicker?: string | null;
  allocating?: boolean;
  onApplyConfig: (config: FolioPortfolioConfig) => void;
  onApplyShares: (
    sharesByTicker: Record<string, number>,
    manualSharesByTicker: Record<string, boolean>,
  ) => void;
  onApplyOpenDate: (ticker: string, openDate: string | null) => void;
  onAddHolding: (ticker: string, market: MarketCode) => void;
  onRemoveHolding: (ticker: string, market: MarketCode) => void;
  onAutoAllocate: (market: MarketCode) => void;
}

const KPI_LABEL_KEYS: Record<
  FolioKpiMetric['key'],
  'folio.kpiNetValue' | 'folio.kpiCumulativeReturn' | 'folio.kpiSharpe' | 'folio.kpiMaxDrawdown'
> = {
  netValue: 'folio.kpiNetValue',
  cumulativeReturn: 'folio.kpiCumulativeReturn',
  sharpe: 'folio.kpiSharpe',
  maxDrawdown: 'folio.kpiMaxDrawdown',
};

const KPI_KEYS: FolioKpiMetric['key'][] = ['netValue', 'cumulativeReturn', 'sharpe', 'maxDrawdown'];

const CHART_W = 640;
const CHART_H = 180;

const EMPTY_KPI: FolioKpiMetric[] = KPI_KEYS.map((key) => ({
  key,
  value: '—',
}));

export function FolioOverviewPanel({
  portfolio,
  loading = false,
  addingTicker = false,
  removingTicker = null,
  allocating = false,
  onApplyConfig,
  onApplyShares,
  onApplyOpenDate,
  onAddHolding,
  onRemoveHolding,
  onAutoAllocate,
}: FolioOverviewPanelProps) {
  const { t } = useTranslation();
  const config = portfolio.config ?? DEFAULT_FOLIO_CONFIG;
  const [draftConfig, setDraftConfig] = useState(config);

  useEffect(() => {
    setDraftConfig(portfolio.config ?? DEFAULT_FOLIO_CONFIG);
  }, [portfolio.config, portfolio.id]);

  const configDirty = useMemo(
    () => JSON.stringify(draftConfig) !== JSON.stringify(portfolio.config ?? DEFAULT_FOLIO_CONFIG),
    [draftConfig, portfolio.config],
  );

  const chart = useMemo(() => {
    const performance = portfolio.performance;
    if (!performance?.portfolio.length || !performance.benchmark.length) {
      return null;
    }
    const values = [...performance.portfolio, ...performance.benchmark];
    const min = Math.min(...values) - 2;
    const max = Math.max(...values) + 2;
    return {
      min,
      max,
      portfolioPath: buildLinePath(performance.portfolio, CHART_W, CHART_H, min, max),
      benchmarkPath: buildLinePath(performance.benchmark, CHART_W, CHART_H, min, max),
      dates: performance.dates,
    };
  }, [portfolio.performance]);

  const kpis = portfolio.kpis?.length ? portfolio.kpis : EMPTY_KPI;

  const updateCapital = (market: MarketCode, value: string) => {
    const parsed = Number(value.replace(/,/g, ''));
    setDraftConfig((prev) => ({
      ...prev,
      capitalByMarket: {
        ...prev.capitalByMarket,
        [market]: Number.isFinite(parsed) && parsed >= 0 ? parsed : 0,
      },
    }));
  };

  const earliestDataDate = portfolio.performance?.dates?.[0] ?? null;

  return (
    <section className="folio-overview">
      <article className="folio-card folio-config">
        <div className="folio-config__grid">
          <label className="folio-config__field">
            <span className="folio-config__label">{t('folio.openDate')}</span>
            <FolioStartDatePicker
              value={draftConfig.startDate}
              earliestDataDate={earliestDataDate}
              onChange={(openDate) =>
                setDraftConfig((prev) => ({
                  ...prev,
                  startDate: openDate,
                  costDate: openDate,
                }))
              }
            />
          </label>
          {FOLIO_MARKETS.map((market) => (
            <label key={market} className="folio-config__field">
              <span className="folio-config__label">
                <FolioMarketLabel market={market} />
              </span>
              <input
                type="number"
                min={0}
                step={10000}
                className="folio-config__input"
                value={draftConfig.capitalByMarket[market]}
                onChange={(event) => updateCapital(market, event.target.value)}
              />
            </label>
          ))}
          <button
            type="button"
            className="folio-config__apply"
            disabled={!configDirty}
            onClick={() => onApplyConfig(draftConfig)}
          >
            {t('folio.applyConfig')}
          </button>
        </div>
        <div className="folio-config__markets-row">
          <div className="folio-config__markets">
            {FOLIO_MARKETS.map((market) => (
              <span key={market} className="folio-config__market-pill">
                <FolioMarketLabel market={market} />
                <span className="folio-config__market-value">
                  {portfolio.netValueByMarket[market] > 0
                    ? formatMarketNetValue(market, portfolio.netValueByMarket[market])
                    : '—'}
                </span>
              </span>
            ))}
          </div>
          <p className="folio-config__hint">{t('folio.configHint')}</p>
        </div>
      </article>

      <div className="folio-kpi-grid">
        {kpis.map((metric) => (
          <article key={metric.key} className="folio-kpi folio-card">
            <span className="folio-kpi__label">{t(KPI_LABEL_KEYS[metric.key])}</span>
            <strong
              className={`folio-kpi__value ${
                metric.value === '—'
                  ? 'folio-tone--muted'
                  : metric.key === 'maxDrawdown'
                    ? 'folio-tone--down'
                    : metric.key === 'sharpe'
                      ? 'folio-tone--accent'
                      : 'folio-tone--up'
              }`}
            >
              {metric.value}
            </strong>
            {metric.delta ? (
              <span
                className={`folio-kpi__delta folio-tone--${
                  metric.deltaTone === 'negative'
                    ? 'down'
                    : metric.deltaTone === 'positive'
                      ? 'up'
                      : 'muted'
                }`}
              >
                {metric.delta}
              </span>
            ) : null}
            {metric.hint ? (
              <span className="folio-kpi__hint">{t('folio.mediumRisk')}</span>
            ) : null}
          </article>
        ))}
      </div>

      <article className="folio-card folio-performance">
        <header className="folio-card__head">
          <h3 className="folio-card__title">{t('folio.performanceChart')}</h3>
          <div className="folio-performance__legend">
            <span className="folio-performance__legend-item folio-performance__legend-item--portfolio">
              {t('folio.performanceLegendPortfolio')}
            </span>
            <span className="folio-performance__legend-item folio-performance__legend-item--benchmark">
              {t('folio.performanceLegendBenchmark')}
            </span>
          </div>
        </header>
        <div className="folio-performance__chart-wrap">
          {chart ? (
            <>
              <svg
                className="folio-performance__chart"
                viewBox={`0 0 ${CHART_W} ${CHART_H}`}
                preserveAspectRatio="none"
                aria-hidden
              >
                <path d={chart.benchmarkPath} className="folio-performance__line folio-performance__line--benchmark" />
                <path d={chart.portfolioPath} className="folio-performance__line folio-performance__line--portfolio" />
              </svg>
              <div className="folio-performance__axis">
                {chart.dates.map((date) => (
                  <span key={date}>{date}</span>
                ))}
              </div>
            </>
          ) : (
            <p className="folio-performance__empty">{t('folio.noPerformanceData')}</p>
          )}
        </div>
      </article>

      <FolioDetailTabs
        portfolio={portfolio}
        loading={loading}
        addingTicker={addingTicker}
        removingTicker={removingTicker}
        allocating={allocating}
        onApplyShares={onApplyShares}
        onApplyOpenDate={onApplyOpenDate}
        onAddHolding={onAddHolding}
        onRemoveHolding={onRemoveHolding}
        onAutoAllocate={onAutoAllocate}
      />
    </section>
  );
}
