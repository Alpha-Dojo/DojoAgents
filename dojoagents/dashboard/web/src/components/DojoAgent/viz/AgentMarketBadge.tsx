import type { MarketCode } from '../../../types/dojoMesh';
import { MARKET_CODE, MARKET_FLAG } from '../../../utils/marketDisplay';

interface AgentMarketBadgeProps {
  market: MarketCode | string;
  compact?: boolean;
}

export function AgentMarketBadge({ market, compact = false }: AgentMarketBadgeProps) {
  const code = String(market).toLowerCase() as MarketCode;
  const label = MARKET_CODE[code] ?? String(market).toUpperCase();
  const flag = MARKET_FLAG[code] ?? '';

  return (
    <span
      className={`agent-market-badge agent-market-badge--${code}${compact ? ' agent-market-badge--compact' : ''}`}
    >
      {flag ? (
        <span className="agent-market-badge__flag" aria-hidden>
          {flag}
        </span>
      ) : null}
      <span className="agent-market-badge__code">{label}</span>
    </span>
  );
}
