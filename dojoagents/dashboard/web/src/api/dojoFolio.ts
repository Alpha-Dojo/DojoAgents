import { fetchJson } from './http';
import {
  addMockFolioHolding,
  autoAllocateMockFolioPortfolio,
  createMockFolioPortfolio,
  deleteMockFolioPortfolio,
  fetchMockFolioPortfolioDetail,
  fetchMockFolioPortfolios,
  updateMockFolioPortfolio,
  USE_INTERACTIVE_MOCKS,
} from '../mocks/interactiveMockData';
import type { MarketCode } from '../types/dojoMesh';
import type {
  FolioHolding,
  FolioKpiMetric,
  FolioPortfolioConfig,
  FolioPortfolioKind,
} from '../types/dojoFolio';
import { mapApiSearchHits, type FolioPortfolioSearchHit } from '../utils/folioPortfolioSearch';

const API_PREFIX = '/api/v1';

export interface FolioPortfolioSummaryResponse {
  id: string;
  name: string;
  subtitle?: string | null;
  kind: FolioPortfolioKind;
  today_change?: number | null;
  net_value_usd?: number | null;
}

export interface FolioPortfolioDetailResponse extends FolioPortfolioSummaryResponse {
  config?: {
    start_date?: string;
    cost_date?: string;
    capital_by_market?: Partial<Record<MarketCode, number>>;
  } | null;
  holdings?: Array<{
    ticker: string;
    name: string;
    market: MarketCode;
    shares: number;
    weight: number;
    cost: number;
    open_date?: string | null;
    uses_default_open_date?: boolean;
    manual_shares?: boolean;
    price: number;
    change_percent: number;
    sector: string;
    market_value: number;
  }>;
  kpis?: Array<{
    key: FolioKpiMetric['key'];
    value: string;
    delta?: string | null;
    delta_tone?: FolioKpiMetric['deltaTone'] | null;
    hint?: string | null;
  }> | null;
  performance?: {
    dates: string[];
    portfolio: number[];
    benchmark: number[];
  } | null;
  net_value_by_market?: Partial<Record<MarketCode, number>> | null;
}

function mapHolding(raw: NonNullable<FolioPortfolioDetailResponse['holdings']>[number]): FolioHolding {
  return {
    ticker: raw.ticker,
    name: raw.name,
    market: raw.market,
    shares: raw.shares,
    weight: raw.weight,
    cost: raw.cost,
    openDate: raw.open_date ?? undefined,
    usesDefaultOpenDate: raw.uses_default_open_date ?? true,
    manualShares: raw.manual_shares ?? false,
    price: raw.price,
    changePercent: raw.change_percent,
    sector: raw.sector,
    marketValue: raw.market_value,
  };
}

function mapConfig(raw: FolioPortfolioDetailResponse['config']): FolioPortfolioConfig | null {
  if (!raw?.start_date || !raw.capital_by_market) return null;
  return {
    startDate: raw.start_date,
    costDate: raw.start_date,
    capitalByMarket: {
      us: raw.capital_by_market.us ?? 0,
      sh: raw.capital_by_market.sh ?? 0,
      hk: raw.capital_by_market.hk ?? 0,
    },
  };
}

export function mapFolioPortfolioDetail(raw: FolioPortfolioDetailResponse) {
  const holdings = (raw.holdings ?? []).map(mapHolding);
  const sharesByTicker = Object.fromEntries(
    holdings.map((row) => [row.ticker, row.shares]),
  ) as Record<string, number>;

  return {
    id: raw.id,
    name: raw.name,
    subtitle: raw.subtitle ?? undefined,
    kind: raw.kind,
    config: mapConfig(raw.config),
    holdings,
    sharesByTicker,
    todayChange: raw.today_change ?? null,
    netValueUsd: raw.net_value_usd ?? null,
    netValueByMarket: {
      us: raw.net_value_by_market?.us ?? 0,
      sh: raw.net_value_by_market?.sh ?? 0,
      hk: raw.net_value_by_market?.hk ?? 0,
    },
    kpis: raw.kpis?.map((item) => ({
      key: item.key,
      value: item.value,
      delta: item.delta ?? undefined,
      deltaTone: item.delta_tone ?? undefined,
      hint: item.hint ?? undefined,
    })) ?? null,
    performance: raw.performance ?? null,
  };
}

export type FolioPortfolioDetail = ReturnType<typeof mapFolioPortfolioDetail>;

export async function fetchFolioPortfolios(): Promise<FolioPortfolioSummaryResponse[]> {
  if (USE_INTERACTIVE_MOCKS) return fetchMockFolioPortfolios();
  const raw = await fetchJson<{ items: FolioPortfolioSummaryResponse[] }>(`${API_PREFIX}/portfolio`);
  return raw.items;
}

export async function searchFolioPortfolios(query: string): Promise<FolioPortfolioSearchHit[]> {
  if (USE_INTERACTIVE_MOCKS) {
    const rows = await fetchMockFolioPortfolios();
    const normalized = query.trim().toLowerCase();
    return rows
      .filter((row) => row.name.toLowerCase().includes(normalized))
      .map((row) => ({ portfolioId: row.id, matchType: 'name' }));
  }
  const params = new URLSearchParams({ q: query });
  const raw = await fetchJson<{
    query: string;
    items: Array<{
      id: string;
      match_type: 'name' | 'holding';
      matched_ticker?: string | null;
      matched_name?: string | null;
    }>;
  }>(`${API_PREFIX}/dojo-folio/portfolios/search?${params}`);
  return mapApiSearchHits(raw.items);
}

export async function fetchFolioPortfolioDetail(portfolioId: string): Promise<FolioPortfolioDetail> {
  if (USE_INTERACTIVE_MOCKS) {
    return mapFolioPortfolioDetail(await fetchMockFolioPortfolioDetail(portfolioId));
  }
  const raw = await fetchJson<{ detail: FolioPortfolioDetailResponse }>(
    `${API_PREFIX}/portfolio/${encodeURIComponent(portfolioId)}/analysis`,
  );
  return mapFolioPortfolioDetail(raw.detail);
}

export async function createFolioPortfolio(name: string): Promise<FolioPortfolioDetail> {
  if (USE_INTERACTIVE_MOCKS) {
    return mapFolioPortfolioDetail(await createMockFolioPortfolio(name));
  }
  const raw = await fetchJson<{ detail: FolioPortfolioDetailResponse }>(`${API_PREFIX}/portfolio/manage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action: 'create', name }),
  });
  return mapFolioPortfolioDetail(raw.detail);
}

export async function updateFolioPortfolio(
  portfolioId: string,
  payload: {
    name?: string;
    config?: FolioPortfolioConfig;
    shares_by_ticker?: Record<string, number>;
    manual_shares_by_ticker?: Record<string, boolean>;
    open_date_by_ticker?: Record<string, string | null>;
  },
): Promise<FolioPortfolioDetail> {
  if (USE_INTERACTIVE_MOCKS) {
    return mapFolioPortfolioDetail(await updateMockFolioPortfolio(portfolioId, payload));
  }
  const raw = await fetchJson<{ detail: FolioPortfolioDetailResponse }>(`${API_PREFIX}/portfolio/manage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      action: 'update',
      portfolio_id: portfolioId,
      name: payload.name,
      start_date: payload.config?.startDate,
      capital_by_market: payload.config?.capitalByMarket,
      shares_by_ticker: payload.shares_by_ticker,
      manual_shares_by_ticker: payload.manual_shares_by_ticker,
      open_date_by_ticker: payload.open_date_by_ticker,
    }),
  });
  return mapFolioPortfolioDetail(raw.detail);
}

export async function deleteFolioPortfolio(portfolioId: string): Promise<void> {
  if (USE_INTERACTIVE_MOCKS) {
    await deleteMockFolioPortfolio(portfolioId);
    return;
  }
  await fetchJson(`${API_PREFIX}/portfolio/manage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action: 'delete', portfolio_id: portfolioId }),
  });
}

export async function addFolioHolding(
  portfolioId: string,
  payload: { ticker: string; market?: MarketCode; shares?: number },
): Promise<FolioPortfolioDetail> {
  if (USE_INTERACTIVE_MOCKS) {
    return mapFolioPortfolioDetail(await addMockFolioHolding(portfolioId, payload));
  }
  const raw = await fetchJson<{ detail: FolioPortfolioDetailResponse }>(`${API_PREFIX}/portfolio/holdings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      portfolio_id: portfolioId,
      ticker: payload.ticker,
      market: payload.market === 'sh' ? 'cn' : payload.market,
      shares: payload.shares,
    }),
  });
  return mapFolioPortfolioDetail(raw.detail);
}

export async function removeFolioHolding(
  portfolioId: string,
  payload: { ticker: string; market?: MarketCode },
): Promise<FolioPortfolioDetail> {
  const market = payload.market === 'sh' ? 'cn' : payload.market;
  const raw = await fetchJson<{ detail: FolioPortfolioDetailResponse }>(`${API_PREFIX}/portfolio/holdings`, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      portfolio_id: portfolioId,
      ticker: payload.ticker,
      market,
    }),
  });
  return mapFolioPortfolioDetail(raw.detail);
}

export async function autoAllocateFolioPortfolio(
  portfolioId: string,
  market?: MarketCode,
): Promise<FolioPortfolioDetail> {
  if (USE_INTERACTIVE_MOCKS) {
    return mapFolioPortfolioDetail(await autoAllocateMockFolioPortfolio(portfolioId, market));
  }
  const raw = await fetchJson<{ detail: FolioPortfolioDetailResponse }>(`${API_PREFIX}/portfolio/allocate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      portfolio_id: portfolioId,
      market: market === 'sh' ? 'cn' : market,
    }),
  });
  return mapFolioPortfolioDetail(raw.detail);
}
