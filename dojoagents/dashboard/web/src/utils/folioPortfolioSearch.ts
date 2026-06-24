import type { FolioPortfolioListItem } from '../hooks/useFolioPortfolios';

export type FolioPortfolioMatchType = 'name' | 'holding';

export interface FolioPortfolioSearchHit {
  portfolioId: string;
  matchType: FolioPortfolioMatchType;
  matchedLabel?: string;
}

export interface FolioPortfolioHoldingsPreview {
  ticker: string;
  name: string;
}

function normalizeQuery(query: string): string {
  return query.trim().toLowerCase();
}

export function searchPortfoliosClient(
  query: string,
  portfolios: FolioPortfolioListItem[],
  holdingsByPortfolioId: Record<string, FolioPortfolioHoldingsPreview[]>,
): FolioPortfolioSearchHit[] {
  const normalized = normalizeQuery(query);
  if (!normalized) return [];

  const hits: FolioPortfolioSearchHit[] = [];
  const seen = new Set<string>();

  for (const portfolio of portfolios) {
    if (portfolio.name.toLowerCase().includes(normalized)) {
      hits.push({ portfolioId: portfolio.id, matchType: 'name' });
      seen.add(portfolio.id);
    }
  }

  for (const portfolio of portfolios) {
    if (seen.has(portfolio.id)) continue;
    const holdings = holdingsByPortfolioId[portfolio.id] ?? [];
    for (const holding of holdings) {
      const tickerMatch = holding.ticker.toLowerCase().includes(normalized);
      const nameMatch = holding.name.toLowerCase().includes(normalized);
      if (tickerMatch || nameMatch) {
        hits.push({
          portfolioId: portfolio.id,
          matchType: 'holding',
          matchedLabel: tickerMatch ? holding.ticker : holding.name,
        });
        seen.add(portfolio.id);
        break;
      }
    }
  }

  return hits;
}

export function mapApiSearchHits(
  rows: Array<{
    id: string;
    match_type: FolioPortfolioMatchType;
    matched_ticker?: string | null;
    matched_name?: string | null;
  }>,
): FolioPortfolioSearchHit[] {
  return rows.map((row) => ({
    portfolioId: row.id,
    matchType: row.match_type,
    matchedLabel: row.matched_ticker ?? row.matched_name ?? undefined,
  }));
}
