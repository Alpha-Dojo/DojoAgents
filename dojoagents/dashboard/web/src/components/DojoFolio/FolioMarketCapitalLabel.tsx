import { useTranslation } from '../../hooks/useTranslation';
import type { MarketCode } from '../../types/dojoMesh';
import { MARKET_FLAG_IMAGE } from '../../utils/marketDisplay';

const LABEL_KEY: Record<MarketCode, 'folio.marketInitialUs' | 'folio.marketInitialCn' | 'folio.marketInitialHk'> = {
  us: 'folio.marketInitialUs',
  cn: 'folio.marketInitialCn',
  hk: 'folio.marketInitialHk',
};

interface FolioMarketCapitalLabelProps {
  market: MarketCode;
}

export function FolioMarketCapitalLabel({ market }: FolioMarketCapitalLabelProps) {
  const { t } = useTranslation();
  return (
    <span className={`folio-market-label folio-market-label--${market} folio-market-label--capital`}>
      <img className="folio-market-label__flag" src={MARKET_FLAG_IMAGE[market]} alt="" aria-hidden />
      <span className="folio-market-label__code">{t(LABEL_KEY[market])}</span>
    </span>
  );
}
