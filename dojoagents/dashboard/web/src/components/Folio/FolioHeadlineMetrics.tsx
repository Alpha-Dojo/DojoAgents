import { useMemo } from 'react';
import type { FolioPortfolioDetail } from '../../api/folio';
import { useTranslation } from '../../hooks/useTranslation';
import { computeFolioHeadlineMetrics } from '../../utils/folioHeadlineMetrics';
import { formatFolioCompactCurrency, formatSignedPercent } from '../../utils/folioFormat';

interface FolioHeadlineMetricsProps {
  portfolio: FolioPortfolioDetail;
  benchmarkSymbol: string | null;
  benchmarkLabel: string;
  loading?: boolean;
}

function toneClass(value: number | null | undefined): string {
  if (value == null || value === 0) return 'folio-headline__value--neutral';
  return value > 0 ? 'folio-headline__value--pos' : 'folio-headline__value--neg';
}

function formatUsdDelta(value: number | null): string {
  if (value == null || !Number.isFinite(value) || value === 0) return '—';
  const sign = value > 0 ? '+' : '';
  return `${sign}${formatFolioCompactCurrency(value, 'USD')}`;
}

function formatPctDelta(value: number | null): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return formatSignedPercent(value);
}

export function FolioHeadlineMetrics({
  portfolio,
  benchmarkSymbol,
  benchmarkLabel,
  loading = false,
}: FolioHeadlineMetricsProps) {
  const { t } = useTranslation();
  const metrics = useMemo(
    () => computeFolioHeadlineMetrics(portfolio, benchmarkSymbol),
    [benchmarkSymbol, portfolio],
  );

  const alphaLabel = t('folio.headlineAlpha', { benchmark: benchmarkLabel });

  return (
    <section className="folio-headline" aria-busy={loading}>
      <article className="folio-headline__card">
        <span className="folio-headline__title">{alphaLabel}</span>
        <p className={`folio-headline__value ${toneClass(metrics.alpha.pct)}`}>
          <span className="folio-headline__primary">{formatUsdDelta(metrics.alpha.usd)}</span>
          <span className="folio-headline__secondary">({formatPctDelta(metrics.alpha.pct)})</span>
        </p>
      </article>
      <article className="folio-headline__card">
        <span className="folio-headline__title">{t('folio.headlineTotalPnl')}</span>
        <p className={`folio-headline__value ${toneClass(metrics.totalPnl.pct)}`}>
          <span className="folio-headline__primary">{formatPctDelta(metrics.totalPnl.pct)}</span>
          <span className="folio-headline__secondary">/ {formatUsdDelta(metrics.totalPnl.usd)}</span>
        </p>
      </article>
      <article className="folio-headline__card">
        <span className="folio-headline__title">{t('folio.headlineDailyDelta')}</span>
        <p className={`folio-headline__value ${toneClass(metrics.dailyDelta)}`}>
          <span className="folio-headline__primary">{formatPctDelta(metrics.dailyDelta)}</span>
        </p>
      </article>
    </section>
  );
}
