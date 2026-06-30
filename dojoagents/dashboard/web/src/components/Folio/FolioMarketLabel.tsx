import type { MarketCode } from '../../types/market';
import { MARKET_CODE, MARKET_FLAG_IMAGE } from '../../utils/marketDisplay';

interface FolioMarketLabelProps {
  market: MarketCode;
}

export function FolioMarketLabel({ market }: FolioMarketLabelProps) {
  return (
    <span className={`folio-market-label folio-market-label--${market}`}>
      <img className="folio-market-label__flag" src={MARKET_FLAG_IMAGE[market]} alt="" aria-hidden />
      <span className="folio-market-label__code">{MARKET_CODE[market]}</span>
    </span>
  );
}
