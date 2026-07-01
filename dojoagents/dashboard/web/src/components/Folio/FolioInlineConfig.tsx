import { useState } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import type { MarketCode } from '../../types/market';
import type { FolioPortfolioConfig } from '../../types/folio';
import { FOLIO_MARKETS } from '../../types/folio';
import {
  capitalFromDisplayValue,
  capitalToDisplayValue,
  toggleCapitalEnUnit,
  type FolioCapitalEnUnit,
} from '../../utils/folioCapitalInput';
import { MARKET_FLAG } from '../../utils/marketDisplay';
import { FolioStartDatePicker } from './FolioStartDatePicker';

interface FolioInlineConfigProps {
  draftConfig: FolioPortfolioConfig;
  configDirty: boolean;
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

export function FolioInlineConfig({
  draftConfig,
  configDirty,
  onChange,
  onApply,
}: FolioInlineConfigProps) {
  const { t, locale } = useTranslation();
  const [enUnit, setEnUnit] = useState<FolioCapitalEnUnit>('M');
  const isZh = locale === 'zh';

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
      <article className="folio-headline__card">
        <span className="folio-headline__title">{t('folio.openDate')}</span>
        <div className="folio-config-inline__body">
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
      </article>

      {FOLIO_MARKETS.map((market) => (
        <article key={market} className="folio-headline__card">
          <span className="folio-headline__title folio-config-inline__title">
            <span className="folio-headline__market-flag" aria-hidden>
              {MARKET_FLAG[market]}
            </span>
            {t(MARKET_TITLE_KEY[market])}
          </span>
          <div className="folio-config-inline__body">
            <div className="folio-config-inline__amount">
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
            </div>
          </div>
        </article>
      ))}

      <button
        type="button"
        className="folio-headline__card folio-config-inline__apply"
        disabled={!configDirty}
        onClick={onApply}
      >
        {t('folio.applyConfig')}
      </button>
    </section>
  );
}
