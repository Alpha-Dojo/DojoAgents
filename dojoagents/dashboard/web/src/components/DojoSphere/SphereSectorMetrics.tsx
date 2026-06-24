import { useMemo, useState } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import type { MarketCode } from '../../types/dojoMesh';
import type { SectorPathSelection, SectorTaxonomyDocument } from '../../types/sectorTaxonomy';
import type {
  SectorLevelKey,
  SectorPerformanceResponse,
  SectorScopeMetricsResponse,
} from '../../types/dojoSphere';
import { MARKET_CODE, MARKET_FLAG } from '../../utils/marketDisplay';
import { formatMarketCapChart, formatPeChart } from '../../utils/marketStats';
import { SphereLevelPerformanceSparkline } from './SphereLevelPerformanceSparkline';
import { SphereLevelRiskMetrics } from './SphereLevelRiskMetrics';
import { SphereLevelSectorSelect } from './SphereLevelSectorSelect';

interface SphereSectorMetricsProps {
  taxonomy: SectorTaxonomyDocument;
  selection: SectorPathSelection;
  onSelectionChange: (next: SectorPathSelection) => void;
  metrics: SectorScopeMetricsResponse | null;
  metricsLoading: boolean;
  performanceByLevel: Partial<Record<SectorLevelKey, SectorPerformanceResponse>>;
  performanceLoading: boolean;
  selectedLevel: SectorLevelKey;
  onSelectLevel: (level: SectorLevelKey) => void;
}

const MARKETS: MarketCode[] = ['us', 'sh', 'hk'];
const LEVELS: SectorLevelKey[] = ['L1', 'L2', 'L3'];

interface ColumnModel {
  market: MarketCode;
  value: number;
  label: string;
  heightPct: number;
}

interface MetricPanelModel {
  columns: ColumnModel[];
}

function buildColumns(
  values: Array<{ market: MarketCode; value: number }>,
  format: (value: number) => string,
): MetricPanelModel {
  const max = Math.max(...values.map((item) => item.value), 1);
  return {
    columns: values.map(({ market, value }) => ({
      market,
      value,
      label: value > 0 ? format(value) : '—',
      heightPct: value > 0 ? Math.max((value / max) * 100, 12) : 0,
    })),
  };
}

interface VerticalColumnPanelProps {
  title: string;
  columns: ColumnModel[];
  loading: boolean;
  hasMetrics: boolean;
}

function VerticalColumnPanel({ title, columns, loading, hasMetrics }: VerticalColumnPanelProps) {
  return (
    <section className="sphere-metric-panel">
      <h4 className="sphere-metric-panel__title">{title}</h4>
      <div className="sphere-metric-panel__plot" aria-label={title}>
        {columns.map((col) => (
          <div key={col.market} className={`sphere-metric-panel__slot sphere-metric-panel__slot--${col.market}`}>
            <span className="sphere-metric-panel__value">{col.value > 0 ? col.label : '—'}</span>
            <div className="sphere-metric-panel__track">
              <div
                className={`sphere-metric-panel__bar sphere-metric-panel__bar--${col.market}${
                  loading && !hasMetrics ? ' sphere-metric-panel__bar--loading' : ''
                }`}
                style={{
                  height:
                    col.value > 0
                      ? `${col.heightPct}%`
                      : loading && !hasMetrics
                        ? '12%'
                        : '0%',
                }}
              />
            </div>
            <div className="sphere-metric-panel__market">
              <span className="sphere-metric-panel__flag" aria-hidden>
                {MARKET_FLAG[col.market]}
              </span>
              <span className="sphere-metric-panel__code">{MARKET_CODE[col.market]}</span>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

export function SphereSectorMetrics({
  taxonomy,
  selection,
  onSelectionChange,
  metrics,
  metricsLoading,
  performanceByLevel,
  performanceLoading,
  selectedLevel,
  onSelectLevel,
}: SphereSectorMetricsProps) {
  const { t } = useTranslation();
  const [syncHoverDate, setSyncHoverDate] = useState<string | null>(null);
  const cards = useMemo(() => {
    return LEVELS.map((level) => {
      const caps = MARKETS.map((market) => ({
        market,
        value: metrics?.scopes?.[level]?.[market]?.total_market_cap ?? 0,
      }));
      const pes = MARKETS.map((market) => ({
        market,
        value: metrics?.scopes?.[level]?.[market]?.weighted_pe ?? 0,
      }));
      const memberCounts = MARKETS.map((market) => ({
        market,
        count: metrics?.scopes?.[level]?.[market]?.member_count ?? null,
      }));

      return {
        level,
        memberCounts,
        capPanel: buildColumns(caps, formatMarketCapChart),
        pePanel: buildColumns(pes, (value) => formatPeChart(value > 0 ? value : null)),
      };
    });
  }, [metrics]);

  return (
    <div className="sphere-sector-metrics" aria-busy={metricsLoading || performanceLoading}>
      <div className="sphere-sector-metrics__cards">
        {cards.map((card) => {
          const isSelected = card.level === selectedLevel;
          return (
            <article
              key={card.level}
              role="button"
              tabIndex={0}
              aria-pressed={isSelected}
              className={`sphere-level-card${isSelected ? ' sphere-level-card--current' : ''}`}
              onClick={() => onSelectLevel(card.level)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  onSelectLevel(card.level);
                }
              }}
            >
              <header className="sphere-level-card__head">
                <h3 className="sphere-level-card__title">
                  <span className="sphere-level-card__level">{card.level}</span>
                  <SphereLevelSectorSelect
                    level={card.level}
                    taxonomy={taxonomy}
                    selection={selection}
                    onChange={onSelectionChange}
                  />
                  <span className="sphere-level-card__title-sep" aria-hidden>
                    ·
                  </span>
                  <span className="sphere-level-card__meta">
                    <span className="sphere-level-card__counts" aria-label={t('sphere.memberCounts')}>
                      {card.memberCounts.map((item, index) => (
                        <span key={item.market}>
                          {index > 0 ? (
                            <span className="sphere-level-card__count-sep">/</span>
                          ) : null}
                          <span
                            className={`sphere-level-card__count sphere-level-card__count--${item.market}`}
                          >
                            {item.count != null ? item.count : '—'}
                          </span>
                        </span>
                      ))}
                    </span>
                    {isSelected && (
                      <span className="sphere-level-card__badge">{t('sphere.currentLevel')}</span>
                    )}
                  </span>
                </h3>
              </header>

              <div className="sphere-level-card__charts">
                <VerticalColumnPanel
                  title={t('sphere.marketCapColumn')}
                  columns={card.capPanel.columns}
                  loading={metricsLoading}
                  hasMetrics={metrics != null}
                />
                <VerticalColumnPanel
                  title={t('sphere.weightedPeTtm')}
                  columns={card.pePanel.columns}
                  loading={metricsLoading}
                  hasMetrics={metrics != null}
                />
              </div>

              <div
                className="sphere-level-card__analytics"
                onClick={(event) => event.stopPropagation()}
                onKeyDown={(event) => event.stopPropagation()}
              >
                <section className="sphere-level-card__module sphere-level-card__module--performance">
                  <SphereLevelPerformanceSparkline
                    seriesByMarket={performanceByLevel[card.level]?.series_by_market}
                    loading={performanceLoading}
                    hoverDate={syncHoverDate}
                    onHoverDateChange={setSyncHoverDate}
                  />
                </section>
                <section className="sphere-level-card__module sphere-level-card__module--risk">
                  <SphereLevelRiskMetrics
                    performance={performanceByLevel[card.level]}
                    loading={performanceLoading}
                  />
                </section>
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}
