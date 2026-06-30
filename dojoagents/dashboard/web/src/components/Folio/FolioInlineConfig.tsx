import { useTranslation } from '../../hooks/useTranslation';
import type { MarketCode } from '../../types/market';
import type { FolioPortfolioConfig } from '../../types/folio';
import { FOLIO_MARKETS } from '../../types/folio';
import { DojoButton } from '../ui';
import { FolioMarketCapitalLabel } from './FolioMarketCapitalLabel';
import { FolioStartDatePicker } from './FolioStartDatePicker';

interface FolioInlineConfigProps {
  draftConfig: FolioPortfolioConfig;
  configDirty: boolean;
  onChange: (config: FolioPortfolioConfig) => void;
  onApply: () => void;
}

export function FolioInlineConfig({
  draftConfig,
  configDirty,
  onChange,
  onApply,
}: FolioInlineConfigProps) {
  const { t } = useTranslation();
  const configHint = t('folio.configHint');

  const updateCapital = (market: MarketCode, value: string) => {
    const parsed = Number(value.replace(/,/g, ''));
    onChange({
      ...draftConfig,
      capitalByMarket: {
        ...draftConfig.capitalByMarket,
        [market]: Number.isFinite(parsed) && parsed >= 0 ? parsed : 0,
      },
    });
  };

  return (
    <div className="folio-config folio-config--inline">
      <div className="folio-config__grid folio-config__grid--inline">
        <label className="folio-config__field">
          <span className="folio-config__label" title={configHint}>
            {t('folio.openDate')}
          </span>
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
        </label>
        {FOLIO_MARKETS.map((market) => (
          <label key={market} className="folio-config__field">
            <span className="folio-config__label" title={configHint}>
              <FolioMarketCapitalLabel market={market} />
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
        <DojoButton
          variant="primary"
          size="sm"
          className="folio-config__apply-inline"
          disabled={!configDirty}
          onClick={onApply}
        >
          {t('folio.applyConfig')}
        </DojoButton>
      </div>
    </div>
  );
}
