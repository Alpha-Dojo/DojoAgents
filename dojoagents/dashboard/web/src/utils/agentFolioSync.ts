import { fetchFolioPortfolioDetail } from '../api/dojoFolio';
import { cacheKeys } from '../cache/cacheKeys';
import { invalidateCache } from '../cache/queryCache';
import { publishFolioListRefresh, publishFolioPortfolioUpdate } from '../navigation/folio_sync';

const PORTFOLIO_MUTATING_TOOLS = new Set([
  'manage_portfolio',
  'add_portfolio_holding',
  'add_portfolio_holdings',
  'auto_allocate_portfolio',
]);

export interface AgentPortfolioMutation {
  portfolio_id?: string;
  name?: string;
  holdings_count?: number;
  tickers?: string[];
}

export async function syncFolioFromAgentTool(
  tool: string,
  ok: boolean,
  data?: AgentPortfolioMutation | null,
): Promise<void> {
  if (!ok || !PORTFOLIO_MUTATING_TOOLS.has(tool)) return;

  const portfolioId = data?.portfolio_id;
  const action =
    tool === 'manage_portfolio' && data?.name ? ('create' as const) : ('update' as const);

  invalidateCache(cacheKeys.folioPortfolios());
  publishFolioListRefresh({ portfolioId, action });

  if (!portfolioId) return;

  try {
    const detail = await fetchFolioPortfolioDetail(portfolioId, { includePerformance: true });
    publishFolioPortfolioUpdate(detail, { action });
  } catch {
    invalidateCache(cacheKeys.folioPortfolios());
    publishFolioListRefresh({ portfolioId, action });
  }
}

export function syncFolioAfterAgentSession(
  tools: Array<{ tool: string; ok?: boolean }>,
): void {
  if (tools.some((item) => item.ok && PORTFOLIO_MUTATING_TOOLS.has(item.tool))) {
    publishFolioListRefresh();
  }
}
