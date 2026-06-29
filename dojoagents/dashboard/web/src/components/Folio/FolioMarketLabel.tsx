import type { MarketCode } from '../../types/market';
import { MARKET_CODE, MARKET_FLAG } from '../../utils/marketDisplay';

interface FolioMarketLabelProps {
  market: MarketCode;
}

export function FolioMarketLabel({ market }: FolioMarketLabelProps) {
  return (
    <span className={`folio-market-label folio-market-label--${market}`}>
      <span className="folio-market-label__flag" aria-hidden>
        {MARKET_FLAG[market]}
      </span>
      <span className="folio-market-label__code">{MARKET_CODE[market]}</span>
    </span>
  );
}
