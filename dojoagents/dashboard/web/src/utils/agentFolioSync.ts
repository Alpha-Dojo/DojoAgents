import { fetchFolioPortfolioDetail } from '../api/folio';
import { cacheKeys } from '../cache/cacheKeys';
import { invalidateCache } from '../cache/queryCache';
import {
  publishFolioListRefresh,
  publishFolioPortfolioUpdate,
  type FolioUpdateAction,
} from '../navigation/folio_sync';

const PORTFOLIO_MUTATING_TOOLS = new Set([
  'manage_portfolio',
  'add_portfolio_holding',
  'add_portfolio_holdings',
  'auto_allocate_portfolio',
  'portfolio_write_create',
  'portfolio_write_rename',
  'portfolio_write_delete',
  'portfolio_write_add_holding',
  'portfolio_write_add_holdings',
  'portfolio_write_remove_holding',
  'portfolio_write_remove_candidates',
  'portfolio_write_auto_allocate',
  'portfolio_write_create_order',
  'portfolio_write_create_orders',
  'portfolio_write_sync_positions',
]);

export interface AgentPortfolioMutation {
  portfolio_id?: string;
  id?: string;
  name?: string;
  action?: string;
  holdings_count?: number;
  tickers?: string[];
}

function portfolioIdFromData(data?: AgentPortfolioMutation | null): string | undefined {
  if (!data) return undefined;
  const raw = data.portfolio_id ?? data.id;
  return typeof raw === 'string' && raw.trim() ? raw.trim() : undefined;
}

function actionFromTool(tool: string, data?: AgentPortfolioMutation | null): FolioUpdateAction {
  if (tool === 'portfolio_write_create') return 'create';
  if (tool === 'manage_portfolio') {
    if (data?.action === 'create') return 'create';
    if (data?.name && !portfolioIdFromData(data)) return 'create';
  }
  return 'update';
}

function isPortfolioResourceChange(change: Record<string, unknown>): boolean {
  return change.resource === 'portfolio';
}

async function syncPortfolioMutation(
  portfolioId?: string,
  action: FolioUpdateAction = 'update',
): Promise<void> {
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

export async function syncFolioFromAgentTool(
  tool: string,
  ok: boolean,
  data?: AgentPortfolioMutation | null,
  resourceChanges?: Record<string, unknown>[] | null,
): Promise<void> {
  if (!ok) return;

  const portfolioChanges = (resourceChanges ?? []).filter(isPortfolioResourceChange);
  if (portfolioChanges.length > 0) {
    for (const change of portfolioChanges) {
      const portfolioId =
        typeof change.portfolio_id === 'string'
          ? change.portfolio_id
          : portfolioIdFromData(data);
      const action: FolioUpdateAction = change.action === 'create' ? 'create' : 'update';
      await syncPortfolioMutation(portfolioId, action);
    }
    return;
  }

  if (!PORTFOLIO_MUTATING_TOOLS.has(tool)) return;

  const portfolioId = portfolioIdFromData(data);
  const action = actionFromTool(tool, data);
  await syncPortfolioMutation(portfolioId, action);
}

export function syncFolioAfterAgentSession(
  tools: Array<{ tool: string; ok?: boolean }>,
): void {
  if (tools.some((item) => item.ok && PORTFOLIO_MUTATING_TOOLS.has(item.tool))) {
    publishFolioListRefresh();
  }
}
