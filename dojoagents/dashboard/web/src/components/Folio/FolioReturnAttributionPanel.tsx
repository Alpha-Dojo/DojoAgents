import { useMemo } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import type { FolioPortfolioDetail } from '../../api/folio';
import { formatSignedPercent } from '../../utils/folioFormat';
import {
  computeReturnAttribution,
  type AttributionStepKey,
  type AttributionWaterfallStep,
} from '../../utils/folioReturnAttribution';
import { LoadingIndicator } from '../ui/LoadingIndicator';

interface FolioReturnAttributionPanelProps {
  portfolio: FolioPortfolioDetail;
  loading?: boolean;
  benchmarkSymbol: string | null;
  benchmarkLabel: string;
}

const STEP_LABEL: Record<AttributionStepKey, string> = {
  benchmark: 'folio.attrStepBenchmark',
  sector: 'folio.attrStepSector',
  stock: 'folio.attrStepStock',
  trading: 'folio.attrStepTrading',
  total: 'folio.attrStepTotal',
};

const TAG_LABEL = {
  overweight: 'folio.attrTagOverweight',
  underweight: 'folio.attrTagUnderweight',
  selection: 'folio.attrTagSelection',
} as const;

function WaterfallChart({
  steps,
  benchmarkLabel,
  benchmarkReturnPct,
}: {
  steps: AttributionWaterfallStep[];
  benchmarkLabel: string;
  benchmarkReturnPct: number;
}) {
  const { t } = useTranslation();
  const plotSteps = steps.filter((step) => step.key !== 'total');
  const values = plotSteps.flatMap((step) => [step.cumulativePct - step.deltaPct, step.cumulativePct]);
  const min = Math.min(0, ...values, benchmarkReturnPct) - 1;
  const max = Math.max(...values, benchmarkReturnPct) + 1;
  const span = max - min || 1;
  const toY = (value: number) => 120 - ((value - min) / span) * 96;
  const barWidth = 52;
  const gap = 18;
  const startX = 36;

  return (
    <div className="folio-attr__waterfall-wrap">
      <p className="folio-attr__benchmark-line">
        {t('folio.attrBenchmarkLine', {
          label: benchmarkLabel,
          value: formatSignedPercent(benchmarkReturnPct),
        })}
      </p>
      <svg
        className="folio-attr__waterfall"
        viewBox="0 0 360 150"
        role="img"
        aria-label={t('folio.attributionTitle')}
      >
        {plotSteps.map((step, index) => {
          const x = startX + index * (barWidth + gap);
          const base = step.cumulativePct - step.deltaPct;
          const yTop = toY(Math.max(base, step.cumulativePct));
          const yBottom = toY(Math.min(base, step.cumulativePct));
          const height = Math.max(yBottom - yTop, 2);
          const positive = step.deltaPct >= 0;
          return (
            <g key={step.key}>
              <rect
                x={x}
                y={yTop}
                width={barWidth}
                height={height}
                rx={3}
                className={
                  step.key === 'benchmark'
                    ? 'folio-attr__bar folio-attr__bar--benchmark'
                    : positive
                      ? 'folio-attr__bar folio-attr__bar--up'
                      : 'folio-attr__bar folio-attr__bar--down'
                }
              />
              {step.key !== 'benchmark' ? (
                <text x={x + barWidth / 2} y={yTop - 4} className="folio-attr__delta" textAnchor="middle">
                  {formatSignedPercent(step.deltaPct)}
                </text>
              ) : null}
              <text x={x + barWidth / 2} y={138} className="folio-attr__step-label" textAnchor="middle">
                {t(STEP_LABEL[step.key])}
              </text>
            </g>
          );
        })}
        <line x1="20" y1={toY(0)} x2="340" y2={toY(0)} className="folio-attr__axis" />
      </svg>
    </div>
  );
}

function ContributionBars({
  title,
  items,
  tone,
}: {
  title: string;
  items: Array<{ label: string; tag: keyof typeof TAG_LABEL; contributionPct: number }>;
  tone: 'up' | 'down';
}) {
  const { t } = useTranslation();
  const maxAbs = Math.max(...items.map((item) => Math.abs(item.contributionPct)), 0.1);

  return (
    <section className="folio-attr__rank-block">
      <h4 className={`folio-attr__rank-title folio-attr__rank-title--${tone}`}>{title}</h4>
      <ul className="folio-attr__rank-list">
        {items.map((item, index) => (
          <li key={`${item.label}-${index}`} className="folio-attr__rank-item">
            <div className="folio-attr__rank-meta">
              <span className="folio-attr__rank-index">{index + 1}.</span>
              <span className="folio-attr__rank-name">{item.label}</span>
              <span className="folio-attr__rank-tag">({t(TAG_LABEL[item.tag])})</span>
            </div>
            <div className="folio-attr__rank-bar-track">
              <span
                className={`folio-attr__rank-bar folio-attr__rank-bar--${tone}`}
                style={{ width: `${(Math.abs(item.contributionPct) / maxAbs) * 100}%` }}
              />
            </div>
            <span className={`folio-attr__rank-value folio-attr__rank-value--${tone}`}>
              {formatSignedPercent(item.contributionPct)}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function FolioReturnAttributionPanel({
  portfolio,
  loading = false,
  benchmarkSymbol,
  benchmarkLabel,
}: FolioReturnAttributionPanelProps) {
  const { t } = useTranslation();
  const attribution = useMemo(
    () =>
      computeReturnAttribution(
        portfolio.holdings,
        portfolio.performance,
        benchmarkSymbol,
        benchmarkLabel,
      ),
    [benchmarkLabel, benchmarkSymbol, portfolio.holdings, portfolio.performance],
  );

  if (loading && !attribution) {
    return (
      <LoadingIndicator
        className="folio-panel__status"
        label={t('folio.loading')}
        variant="panel"
      />
    );
  }
  if (!attribution) {
    return <p className="folio-panel__status">{t('folio.attributionEmpty')}</p>;
  }

  const insightKey =
    attribution.primaryDriver === 'sector'
      ? 'folio.attrInsightSector'
      : attribution.primaryDriver === 'stock'
        ? 'folio.attrInsightStock'
        : attribution.primaryDriver === 'trading'
          ? 'folio.attrInsightTrading'
          : 'folio.attrInsightMixed';

  return (
    <section className="folio-attr" aria-busy={loading}>
      <div className="folio-attr__grid">
        <WaterfallChart
          steps={attribution.waterfall}
          benchmarkLabel={attribution.benchmarkLabel}
          benchmarkReturnPct={attribution.benchmarkReturnPct}
        />
        <div className="folio-attr__ranks">
          <ContributionBars
            title={t('folio.attrTopPositive')}
            tone="up"
            items={attribution.topPositive}
          />
          <ContributionBars
            title={t('folio.attrTopNegative')}
            tone="down"
            items={attribution.topNegative}
          />
        </div>
      </div>
      <footer className="folio-attr__insight">
        <span className="folio-attr__insight-icon" aria-hidden>
          💡
        </span>
        <p>
          {t(insightKey, {
            sector: attribution.insightSector ?? '—',
            weakSector: attribution.insightWeakSector ?? '—',
          })}
        </p>
      </footer>
    </section>
  );
}
