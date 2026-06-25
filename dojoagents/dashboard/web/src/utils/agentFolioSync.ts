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
  holdings_by_market?: Record<string, number>;
  tickers?: string[];
}

export function syncFolioFromAgentTool(
  tool: string,
  ok: boolean,
  data: unknown,
): Promise<void>;
export function syncFolioFromAgentTool(
  tool: string,
  ok: boolean,
  data?: AgentPortfolioMutation | null,
): Promise<void>;
export async function syncFolioFromAgentTool(
  tool: string,
  ok: boolean,
  data?: unknown,
): Promise<void> {
  if (!ok || !PORTFOLIO_MUTATING_TOOLS.has(tool)) return;

  const portfolioData = data as AgentPortfolioMutation | null | undefined;
  const portfolioId = portfolioData?.portfolio_id;
  const action =
    tool === 'manage_portfolio' && portfolioData?.name ? ('create' as const) : ('update' as const);

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
  const mutated = tools.some((item) => item.ok && PORTFOLIO_MUTATING_TOOLS.has(item.tool));
  if (mutated) {
    publishFolioListRefresh();
  }
}
