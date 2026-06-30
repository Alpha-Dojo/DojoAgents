import { useMemo } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import type { EntityProfitabilityAxis } from '../../types/entity';
import { polarPoint } from '../../utils/entityCharts';
import { LoadingIndicator } from '../ui/LoadingIndicator';
import { EntityCard } from './EntityCard';

interface EntityProfitabilityPanelProps {
  axes: EntityProfitabilityAxis[];
  industryLabel: string;
  loading?: boolean;
}

const CX = 110;
const CY = 100;
const R = 72;

function percentileTone(p: number): 'high' | 'mid' | 'low' {
  if (p >= 85) return 'high';
  if (p >= 70) return 'mid';
  return 'low';
}

export function EntityProfitabilityPanel({ axes, industryLabel, loading = false }: EntityProfitabilityPanelProps) {
  const { t } = useTranslation();

  const radar = useMemo(() => {
    if (!axes.length) {
      return { polygon: '', rings: [] as string[], labels: [] as Array<{ x: number; y: number; key: string }> };
    }
    const count = axes.length;
    const polygon = axes
      .map((axis, i) => {
        const angle = (Math.PI * 2 * i) / count;
        const radius = (axis.value / axis.max) * R;
        return polarPoint(CX, CY, radius, angle);
      })
      .map((p) => `${p.x},${p.y}`)
      .join(' ');

    const rings = [0.25, 0.5, 0.75, 1].map((ratio) =>
      axes
        .map((_, i) => {
          const angle = (Math.PI * 2 * i) / count;
          return polarPoint(CX, CY, R * ratio, angle);
        })
        .map((p) => `${p.x},${p.y}`)
        .join(' '),
    );

    const labels = axes.map((axis, i) => {
      const angle = (Math.PI * 2 * i) / count;
      const p = polarPoint(CX, CY, R + 16, angle);
      return { ...p, key: axis.key };
    });

    return { polygon, rings, labels };
  }, [axes]);

  if (loading && !axes.length) {
    return (
      <EntityCard title={t('entityPage.profitabilityTitle')} className="entity-card--profitability">
        <LoadingIndicator
          className="entity-chart-stage__status"
          label={t('entityPage.finIndicatorsLoading')}
          variant="panel"
        />
      </EntityCard>
    );
  }

  if (!axes.length) {
    return (
      <EntityCard title={t('entityPage.profitabilityTitle')} className="entity-card--profitability">
        <p className="entity-chart-stage__status">{t('entityPage.finIndicatorsEmpty')}</p>
      </EntityCard>
    );
  }

  return (
    <EntityCard title={t('entityPage.profitabilityTitle')} className="entity-card--profitability">
      <div className="core-profitability">
        <div className="core-profitability__radar-wrap">
          <svg viewBox="0 0 220 200" className="core-profitability__radar">
            {radar.rings.map((points, i) => (
              <polygon key={i} points={points} className="core-profitability__ring" />
            ))}
            {axes.map((_, i) => {
              const angle = (Math.PI * 2 * i) / axes.length;
              const p = polarPoint(CX, CY, R, angle);
              return <line key={i} x1={CX} y1={CY} x2={p.x} y2={p.y} className="core-profitability__spoke" />;
            })}
            <polygon points={radar.polygon} className="core-profitability__shape" />
            {radar.labels.map((label) => (
              <text key={label.key} x={label.x} y={label.y} className="core-profitability__axis-label" textAnchor="middle">
                {t(`core.profit.${label.key}` as 'entityPage.profit.grossMargin')}
              </text>
            ))}
          </svg>
        </div>

        <div className="core-profitability__ranks">
          <p className="core-profitability__ranks-title">{t('entityPage.percentileInIndustry', { industry: industryLabel })}</p>
          <ul className="core-profitability__rank-list">
            {axes.map((axis) => {
              const tone = percentileTone(axis.percentile);
              return (
                <li key={axis.key} className="core-profitability__rank-item">
                  <div className="core-profitability__rank-head">
                    <span>{t(`core.profit.${axis.key}` as 'entityPage.profit.grossMargin')}</span>
                    <span className={`core-profitability__rank-value core-profitability__rank-value--${tone}`}>
                      {axis.value.toFixed(1)}%
                    </span>
                  </div>
                  <div className="core-profitability__rank-bar" aria-hidden>
                    <div
                      className={`core-profitability__rank-fill core-profitability__rank-fill--${tone}`}
                      style={{ width: `${axis.percentile}%` }}
                    />
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      </div>
    </EntityCard>
  );
}
