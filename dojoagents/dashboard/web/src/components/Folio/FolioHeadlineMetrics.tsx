import { useMemo } from 'react';
import type { FolioPortfolioDetail } from '../../api/folio';
import { useTranslation } from '../../hooks/useTranslation';
import type { MarketCode } from '../../types/market';
import { computeFolioHeadlineMetrics } from '../../utils/folioHeadlineMetrics';
import { formatCompactAmount, formatSignedPercent } from '../../utils/folioFormat';
import { MARKET_FLAG_IMAGE } from '../../utils/marketDisplay';

interface FolioHeadlineMetricsProps {
  portfolio: FolioPortfolioDetail;
  loading?: boolean;
}

const MARKET_LABEL: Record<MarketCode, string> = {
  us: 'US',
  cn: 'CN',
  hk: 'HK',
};

function toneClass(value: number | null | undefined): string {
  if (value == null || value === 0) return 'folio-headline__value--neutral';
  return value > 0 ? 'folio-headline__value--pos' : 'folio-headline__value--neg';
}

function formatAssets(value: number | null): string {
  if (value == null || !Number.isFinite(value) || value <= 0) return '—';
  return formatCompactAmount(value);
}

function formatPct(value: number | null): string {
  if (value == null || !Number.isFinite(value)) return '0.00%';
  return formatSignedPercent(value);
}

export function FolioHeadlineMetrics({ portfolio, loading = false }: FolioHeadlineMetricsProps) {
  const { t } = useTranslation();
  const metrics = useMemo(() => computeFolioHeadlineMetrics(portfolio), [portfolio]);

  return (
    <section className="folio-headline" aria-busy={loading}>
      <article className="folio-headline__card">
        <span className="folio-headline__title">{t('folio.headlineAssets')}</span>
        <ul className="folio-headline__markets folio-headline__markets--cols">
          {metrics.byMarket.map((row) => (
            <li key={row.market} className="folio-headline__market-col">
              <span className="folio-headline__market-label">
                <img className="folio-headline__market-flag" src={MARKET_FLAG_IMAGE[row.market]} alt="" aria-hidden />
                {MARKET_LABEL[row.market]}
              </span>
              <span className="folio-headline__market-value folio-headline__value--neutral">
                {formatAssets(row.assets)}
              </span>
            </li>
          ))}
        </ul>
      </article>

      <article className="folio-headline__card">
        <span className="folio-headline__title">{t('folio.headlineTotalPnl')}</span>
        <ul className="folio-headline__markets folio-headline__markets--cols">
          {metrics.byMarket.map((row) => (
            <li key={row.market} className="folio-headline__market-col">
              <span className="folio-headline__market-label">
                <img className="folio-headline__market-flag" src={MARKET_FLAG_IMAGE[row.market]} alt="" aria-hidden />
                {MARKET_LABEL[row.market]}
              </span>
              <span className={`folio-headline__market-value ${toneClass(row.totalPnlPct)}`}>
                {formatPct(row.totalPnlPct)}
              </span>
            </li>
          ))}
        </ul>
      </article>

      <article className="folio-headline__card">
        <span className="folio-headline__title">{t('folio.headlineTodayPnl')}</span>
        <ul className="folio-headline__markets folio-headline__markets--cols">
          {metrics.byMarket.map((row) => (
            <li key={row.market} className="folio-headline__market-col">
              <span className="folio-headline__market-label">
                <img className="folio-headline__market-flag" src={MARKET_FLAG_IMAGE[row.market]} alt="" aria-hidden />
                {MARKET_LABEL[row.market]}
              </span>
              <span className={`folio-headline__market-value ${toneClass(row.todayPnlPct)}`}>
                {formatPct(row.todayPnlPct)}
              </span>
            </li>
          ))}
        </ul>
      </article>
    </section>
  );
}
