import { useState } from 'react';
import type { FolioPortfolioDetail } from '../../api/folio';
import { useTranslation } from '../../hooks/useTranslation';
import type { MarketCode } from '../../types/market';
import type { FolioPortfolioConfig } from '../../types/folio';
import { FOLIO_MARKETS } from '../../types/folio';
import { computeFolioHeadlineMetrics } from '../../utils/folioHeadlineMetrics';
import { formatCompactAmount, formatSignedPercent } from '../../utils/folioFormat';
import {
  capitalFromDisplayValue,
  capitalToDisplayValue,
  toggleCapitalEnUnit,
  type FolioCapitalEnUnit,
} from '../../utils/folioCapitalInput';
import { MARKET_FLAG_IMAGE } from '../../utils/marketDisplay';
import { DojoButton } from '../ui';
import { FolioStartDatePicker } from './FolioStartDatePicker';

interface FolioInlineConfigProps {
  portfolio: FolioPortfolioDetail;
  draftConfig: FolioPortfolioConfig;
  configDirty: boolean;
  visibleMarkets?: MarketCode[];
  onChange: (config: FolioPortfolioConfig) => void;
  onApply: () => void;
}

const MARKET_TITLE_KEY: Record<
  MarketCode,
  'folio.marketInitialUs' | 'folio.marketInitialCn' | 'folio.marketInitialHk'
> = {
  us: 'folio.marketInitialUs',
  cn: 'folio.marketInitialCn',
  hk: 'folio.marketInitialHk',
};

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

function formatPct(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '0.00%';
  return formatSignedPercent(value);
}

export function FolioInlineConfig({
  portfolio,
  draftConfig,
  configDirty,
  visibleMarkets = FOLIO_MARKETS,
  onChange,
  onApply,
}: FolioInlineConfigProps) {
  const { t, locale } = useTranslation();
  const [enUnit, setEnUnit] = useState<FolioCapitalEnUnit>('M');
  const isZh = locale === 'zh';
  const metrics = computeFolioHeadlineMetrics(portfolio);
  const metricsByMarket = new Map(metrics.byMarket.map((row) => [row.market, row]));

  const updateCapital = (market: MarketCode, value: string) => {
    onChange({
      ...draftConfig,
      capitalByMarket: {
        ...draftConfig.capitalByMarket,
        [market]: capitalFromDisplayValue(value, locale, enUnit),
      },
    });
  };

  return (
    <section className="folio-config-inline">
      <aside className="folio-config-inline__aside">
        <label className="folio-config-inline__aside-label">{t('folio.openDate')}</label>
        <div className="folio-config-inline__date">
          <FolioStartDatePicker
            value={draftConfig.startDate}
            onChange={(openDate) =>
              onChange({
                ...draftConfig,
                startDate: openDate,
                costDate: openDate,
              })
            }
          />
        </div>

        <DojoButton
          size="sm"
          variant="primary"
          className="folio-config-inline__apply"
          disabled={!configDirty}
          onClick={onApply}
        >
          {t('folio.applyConfig')}
        </DojoButton>
      </aside>

      <div className="folio-config-inline__matrix" role="table" aria-label={t('folio.openConfig')}>
        <div className="folio-config-inline__matrix-head" role="row">
          <span role="columnheader">{t('folio.configMarketColumn')}</span>
          <span role="columnheader">{t('folio.headlineAssets')}</span>
          <span role="columnheader">{t('folio.headlineTotalPnl')}</span>
          <span role="columnheader">{t('folio.headlineTodayPnl')}</span>
          <span role="columnheader">{t('folio.configInitialColumn')}</span>
        </div>

        {visibleMarkets.map((market) => {
          const row = metricsByMarket.get(market);
          return (
            <div key={market} className="folio-config-inline__matrix-row" role="row">
              <span className="folio-config-inline__market" role="cell">
                <img className="folio-headline__market-flag" src={MARKET_FLAG_IMAGE[market]} alt="" aria-hidden />
                {MARKET_LABEL[market]}
              </span>

              <span className="folio-config-inline__metric folio-headline__value--neutral" role="cell">
                {formatAssets(row?.assets ?? null)}
              </span>
              <span className={`folio-config-inline__metric ${toneClass(row?.totalPnlPct)}`} role="cell">
                {formatPct(row?.totalPnlPct)}
              </span>
              <span className={`folio-config-inline__metric ${toneClass(row?.todayPnlPct)}`} role="cell">
                {formatPct(row?.todayPnlPct)}
              </span>

              <span className="folio-config-inline__capital" role="cell" aria-label={t(MARKET_TITLE_KEY[market])}>
                <input
                  type="number"
                  min={0}
                  step={isZh ? 1 : enUnit === 'M' ? 0.1 : 1}
                  className="folio-config__input folio-config-inline__input"
                  value={capitalToDisplayValue(draftConfig.capitalByMarket[market], locale, enUnit)}
                  onChange={(event) => updateCapital(market, event.target.value)}
                />
                {isZh ? (
                  <span className="folio-config-inline__unit">{t('folio.capitalUnitWan')}</span>
                ) : (
                  <button
                    type="button"
                    className="folio-config-inline__unit folio-config-inline__unit--toggle"
                    title={t('folio.capitalUnitToggle')}
                    aria-label={t('folio.capitalUnitToggle')}
                    onClick={() => setEnUnit((prev) => toggleCapitalEnUnit(prev))}
                  >
                    {enUnit}
                  </button>
                )}
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
}
