import { fetchJson, ApiError } from './http';
import type { MarketCode } from '../types/market';
import type {
  FolioAllocationStrategy,
  FolioCandidate,
  FolioCreateOrderPayload,
  FolioHolding,
  FolioKpiMetric,
  FolioOrder,
  FolioOrderSide,
  FolioOrderStatus,
  FolioPortfolioConfig,
  FolioPortfolioKind,
} from '../types/folio';
import { DEFAULT_FOLIO_CONFIG } from '../types/folio';
import { DATA_START_DATE } from '../utils/klineDate';
import { mapApiSearchHits, type FolioPortfolioSearchHit } from '../utils/folioPortfolioSearch';

const API_PREFIX = '/api/v1';

export interface FolioPortfolioSummaryResponse {
  id: string;
  name: string;
  subtitle?: string | null;
  kind: FolioPortfolioKind;
  pinned?: boolean;
  today_change?: number | null;
  net_value_usd?: number | null;
}

export interface FolioPortfolioDetailResponse extends FolioPortfolioSummaryResponse {
  config?: {
    start_date?: string;
    cost_date?: string;
    capital_by_market?: Partial<Record<MarketCode, number>>;
  } | null;
  candidates?: Array<{
    ticker: string;
    name: string;
    name_zh?: string;
    name_en?: string;
    market: MarketCode;
    price: number;
    change_percent: number;
    market_cap: number;
    pe?: number | null;
    pb?: number | null;
    dividend_yield?: number | null;
    eps?: number | null;
    turn_rate?: number | null;
    sector_l1?: string;
    sector_l2?: string;
    sector_l3?: string;
  }>;
  holdings?: Array<{
    ticker: string;
    name: string;
    name_zh?: string;
    name_en?: string;
    market: MarketCode;
    shares: number;
    weight: number;
    cost: number;
    cost_low?: number | null;
    cost_high?: number | null;
    uses_default_cost?: boolean;
    cost_date?: string | null;
    cost_basis?: number;
    open_date?: string | null;
    uses_default_open_date?: boolean;
    shares_locked?: boolean;
    open_date_locked?: boolean;
    cost_locked?: boolean;
    manual_shares?: boolean;
    price: number;
    change_percent: number;
    total_return_pct?: number | null;
    sector: string;
    sector_l1?: string;
    sector_l2?: string;
    sector_l3?: string;
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
    window_start?: string | null;
    window_end?: string | null;
    series_by_market?: Partial<
      Record<
        MarketCode,
        Array<{ date: string; value: number }>
      >
    >;
    benchmark_by_market?: Partial<
      Record<
        MarketCode,
        Array<{ date: string; value: number }>
      >
    >;
    benchmark_symbol_by_market?: Partial<Record<MarketCode, string>>;
    stats_by_market?: Partial<
      Record<
        MarketCode,
        {
          cumulative_return_pct?: number | null;
          volatility_pct?: number | null;
          sharpe_ratio?: number | null;
          calmar_ratio?: number | null;
          max_drawdown_pct?: number | null;
          trading_days?: number;
        }
      >
    >;
    candidate_series_by_market?: Partial<
      Record<
        MarketCode,
        Array<{ date: string; value: number }>
      >
    >;
    candidate_stats_by_market?: Partial<
      Record<
        MarketCode,
        {
          cumulative_return_pct?: number | null;
          volatility_pct?: number | null;
          sharpe_ratio?: number | null;
          calmar_ratio?: number | null;
          max_drawdown_pct?: number | null;
          trading_days?: number;
        }
      >
    >;
  } | null;
  net_value_by_market?: Partial<Record<MarketCode, number>> | null;
  cost_basis_by_market?: Partial<Record<MarketCode, number>> | null;
  orders?: Array<{
    id: string;
    ticker: string;
    name?: string;
    name_zh?: string;
    name_en?: string;
    market: MarketCode;
    order_side: FolioOrderSide;
    order_status: FolioOrderStatus;
    price: number;
    qty: number;
    order_time?: string | null;
    fill_time?: string | null;
    fill_price?: number | null;
    created_at: string;
  }>;
}

interface PortfolioAnalysisResponse {
  id: string;
  name: string;
  subtitle?: string | null;
  benchmark?: string | null;
  start_date?: string | null;
  capital_by_market?: Partial<Record<MarketCode, number>>;
  candidates?: Array<{
    ticker: string;
    name: string;
    name_zh?: string;
    name_en?: string;
    market: MarketCode;
    price: number;
    change_percent: number;
    market_cap: number;
    pe?: number | null;
    pb?: number | null;
    dividend_yield?: number | null;
    eps?: number | null;
    turn_rate?: number | null;
    sector_l1?: string;
    sector_l2?: string;
    sector_l3?: string;
  }>;
  holdings: Array<{
    ticker: string;
    name: string;
    name_zh?: string;
    name_en?: string;
    market: MarketCode;
    shares: number;
    weight: number;
    cost: number;
    cost_low?: number | null;
    cost_high?: number | null;
    uses_default_cost?: boolean;
    cost_date?: string | null;
    open_date?: string | null;
    uses_default_open_date?: boolean;
    cost_basis?: number;
    price: number;
    change_percent: number;
    total_return_pct?: number | null;
    market_value: number;
    sector_l1: string;
    sector_l2: string;
    sector_l3: string;
  }>;
  kpis: Array<{
    key: FolioKpiMetric['key'];
    value: string;
    delta?: string | null;
    delta_tone?: FolioKpiMetric['deltaTone'] | null;
  }>;
  performance_window_start?: string | null;
  performance_window_end?: string | null;
  nav_by_market: Partial<
    Record<MarketCode, Array<{ date: string; value: number }>>
  >;
  candidate_nav_by_market?: Partial<
    Record<MarketCode, Array<{ date: string; value: number }>>
  >;
  benchmark_by_market: Partial<
    Record<MarketCode, Array<{ date: string; value: number }>>
  >;
  benchmark_symbol_by_market?: Partial<Record<MarketCode, string>>;
  stats_by_market: Partial<
    Record<
      MarketCode,
      {
        cumulative_return_pct?: number | null;
        volatility_pct?: number | null;
        sharpe_ratio?: number | null;
        calmar_ratio?: number | null;
        max_drawdown_pct?: number | null;
        trading_days?: number;
      }
    >
  >;
  candidate_stats_by_market?: Partial<
    Record<
      MarketCode,
      {
        cumulative_return_pct?: number | null;
        volatility_pct?: number | null;
        sharpe_ratio?: number | null;
        calmar_ratio?: number | null;
        max_drawdown_pct?: number | null;
        trading_days?: number;
      }
    >
  >;
  net_value_by_market: Partial<Record<MarketCode, number>>;
  cost_basis_by_market?: Partial<Record<MarketCode, number>>;
  orders?: Array<{
    id: string;
    ticker: string;
    name?: string;
    name_zh?: string;
    name_en?: string;
    market: MarketCode;
    order_side: FolioOrderSide;
    order_status: FolioOrderStatus;
    price: number;
    qty: number;
    order_time?: string | null;
    fill_time?: string | null;
    fill_price?: number | null;
    created_at: string;
  }>;
}

interface PortfolioListResponse {
  query?: string | null;
  items: FolioPortfolioSummaryResponse[];
}

function mapOrder(raw: NonNullable<FolioPortfolioDetailResponse['orders']>[number]): FolioOrder {
  return {
    id: raw.id,
    ticker: raw.ticker,
    name: raw.name ?? raw.ticker,
    nameZh: raw.name_zh,
    nameEn: raw.name_en,
    market: raw.market,
    orderSide: raw.order_side,
    orderStatus: raw.order_status,
    price: raw.price,
    qty: raw.qty,
    orderTime: raw.order_time ?? undefined,
    fillTime: raw.fill_time ?? undefined,
    fillPrice: raw.fill_price ?? null,
    createdAt: raw.created_at,
  };
}

function mapCandidate(
  raw: NonNullable<FolioPortfolioDetailResponse['candidates']>[number],
): FolioCandidate {
  return {
    ticker: raw.ticker,
    name: raw.name,
    nameZh: raw.name_zh,
    nameEn: raw.name_en,
    market: raw.market,
    price: raw.price,
    changePercent: raw.change_percent,
    marketCap: raw.market_cap,
    pe: raw.pe ?? null,
    pb: raw.pb ?? null,
    dividendYield: raw.dividend_yield ?? null,
    eps: raw.eps ?? null,
    turnRate: raw.turn_rate ?? null,
    sector: raw.sector_l1 ?? '',
    sectorL1: raw.sector_l1,
    sectorL2: raw.sector_l2,
    sectorL3: raw.sector_l3,
  };
}

function mapHolding(raw: NonNullable<FolioPortfolioDetailResponse['holdings']>[number]): FolioHolding {
  return {
    ticker: raw.ticker,
    name: raw.name,
    nameZh: raw.name_zh,
    nameEn: raw.name_en,
    market: raw.market,
    shares: raw.shares,
    weight: raw.weight,
    cost: raw.cost,
    costLow: raw.cost_low ?? undefined,
    costHigh: raw.cost_high ?? undefined,
    usesDefaultCost: raw.uses_default_cost ?? true,
    costDate: raw.cost_date ?? undefined,
    costBasis: raw.cost_basis ?? raw.cost * raw.shares,
    openDate: raw.open_date ?? undefined,
    usesDefaultOpenDate: raw.uses_default_open_date ?? true,
    sharesLocked: raw.shares_locked ?? raw.manual_shares ?? false,
    openDateLocked: raw.open_date_locked ?? false,
    costLocked: raw.cost_locked ?? false,
    manualShares: raw.manual_shares ?? raw.shares_locked ?? false,
    price: raw.price,
    changePercent: raw.change_percent,
    totalReturnPct:
      raw.total_return_pct ??
      (raw.cost > 0 && raw.price > 0
        ? Number((((raw.price - raw.cost) / raw.cost) * 100).toFixed(2))
        : null),
    sector: raw.sector,
    sectorL1: raw.sector_l1 ?? raw.sector,
    sectorL2: raw.sector_l2 ?? raw.sector,
    sectorL3: raw.sector_l3 ?? raw.sector,
    marketValue: raw.market_value,
  };
}

function mapConfigFromAnalysis(analysis: PortfolioAnalysisResponse): FolioPortfolioConfig {
  const startDate =
    analysis.performance_window_start ??
    analysis.start_date ??
    DATA_START_DATE;
  const capital = analysis.capital_by_market ?? {};
  return {
    startDate,
    costDate: startDate,
    capitalByMarket: {
      us: capital.us ?? DEFAULT_FOLIO_CONFIG.capitalByMarket.us,
      cn: capital.cn ?? DEFAULT_FOLIO_CONFIG.capitalByMarket.cn,
      hk: capital.hk ?? DEFAULT_FOLIO_CONFIG.capitalByMarket.hk,
    },
  };
}

function mapConfig(raw: FolioPortfolioDetailResponse['config']): FolioPortfolioConfig | null {
  if (!raw?.start_date || !raw.capital_by_market) return null;
  return {
    startDate: raw.start_date,
    costDate: raw.start_date,
    capitalByMarket: {
      us: raw.capital_by_market.us ?? 0,
      cn: raw.capital_by_market.cn ?? 0,
      hk: raw.capital_by_market.hk ?? 0,
    },
  };
}

function mapPerformanceStats(
  raw?: Partial<
    Record<
      MarketCode,
      {
        cumulative_return_pct?: number | null;
        volatility_pct?: number | null;
        sharpe_ratio?: number | null;
        calmar_ratio?: number | null;
        max_drawdown_pct?: number | null;
        trading_days?: number;
      }
    >
  >,
) {
  const statsByMarket: Partial<
    Record<
      MarketCode,
      {
        cumulative_return_pct: number | null;
        volatility_pct: number | null;
        sharpe_ratio: number | null;
        calmar_ratio: number | null;
        max_drawdown_pct: number | null;
        trading_days: number;
      }
    >
  > = {};
  if (!raw) return statsByMarket;
  for (const market of ['us', 'cn', 'hk'] as MarketCode[]) {
    const row = raw[market];
    if (!row) continue;
    statsByMarket[market] = {
      cumulative_return_pct: row.cumulative_return_pct ?? null,
      volatility_pct: row.volatility_pct ?? null,
      sharpe_ratio: row.sharpe_ratio ?? null,
      calmar_ratio: row.calmar_ratio ?? null,
      max_drawdown_pct: row.max_drawdown_pct ?? null,
      trading_days: row.trading_days ?? 0,
    };
  }
  return statsByMarket;
}

function mapPerformanceSeries(
  raw?: Partial<Record<MarketCode, Array<{ date: string; value: number }>>>,
) {
  const seriesByMarket: Partial<Record<MarketCode, { date: string; value: number }[]>> = {};
  if (!raw) return seriesByMarket;
  for (const market of ['us', 'cn', 'hk'] as MarketCode[]) {
    if (raw[market]?.length) {
      seriesByMarket[market] = raw[market]!.map((point) => ({
        date: point.date,
        value: Number(point.value),
      }));
    }
  }
  return seriesByMarket;
}

function mapPerformance(raw: FolioPortfolioDetailResponse['performance']) {
  if (!raw) return null;

  return {
    windowStart: raw.window_start ?? null,
    windowEnd: raw.window_end ?? null,
    seriesByMarket: mapPerformanceSeries(raw.series_by_market),
    candidateSeriesByMarket: mapPerformanceSeries(raw.candidate_series_by_market),
    benchmarkByMarket: mapPerformanceSeries(raw.benchmark_by_market),
    benchmarkSymbolByMarket: raw.benchmark_symbol_by_market ?? {},
    statsByMarket: mapPerformanceStats(raw.stats_by_market),
    candidateStatsByMarket: mapPerformanceStats(raw.candidate_stats_by_market),
  };
}

export function mapFolioPortfolioDetail(raw: FolioPortfolioDetailResponse) {
  const positions = (raw.holdings ?? []).map(mapHolding);
  const candidates = (raw.candidates ?? []).map(mapCandidate);
  const sharesByTicker = Object.fromEntries(
    positions.map((row) => [row.ticker, row.shares]),
  ) as Record<string, number>;

  return {
    id: raw.id,
    name: raw.name,
    subtitle: raw.subtitle ?? undefined,
    kind: raw.kind,
    pinned: raw.pinned ?? false,
    config: mapConfig(raw.config),
    candidates,
    positions,
    holdings: positions,
    sharesByTicker,
    todayChange: raw.today_change ?? null,
    netValueUsd: raw.net_value_usd ?? null,
    netValueByMarket: {
      us: raw.net_value_by_market?.us ?? 0,
      cn: raw.net_value_by_market?.cn ?? 0,
      hk: raw.net_value_by_market?.hk ?? 0,
    },
    costBasisByMarket: {
      us: raw.cost_basis_by_market?.us ?? 0,
      cn: raw.cost_basis_by_market?.cn ?? 0,
      hk: raw.cost_basis_by_market?.hk ?? 0,
    },
    kpis: raw.kpis?.map((item) => ({
      key: item.key,
      value: item.value,
      delta: item.delta ?? undefined,
      deltaTone: item.delta_tone ?? undefined,
      hint: item.hint ?? undefined,
    })) ?? null,
    performance: mapPerformance(raw.performance),
    orders: (raw.orders ?? []).map(mapOrder),
  };
}

export type FolioPortfolioDetail = ReturnType<typeof mapFolioPortfolioDetail>;

function mapAnalysisToDetail(
  analysis: PortfolioAnalysisResponse,
  summary?: FolioPortfolioSummaryResponse,
  includePerformance = true,
): FolioPortfolioDetailResponse {
  const netTotal = Object.values(analysis.net_value_by_market ?? {}).reduce(
    (sum, value) => sum + (value ?? 0),
    0,
  );
  const config = mapConfigFromAnalysis(analysis);
  return {
    id: analysis.id,
    name: analysis.name,
    subtitle: analysis.subtitle,
    kind: summary?.kind ?? 'manual',
    pinned: summary?.pinned ?? false,
    today_change: summary?.today_change ?? null,
    net_value_usd: summary?.net_value_usd ?? netTotal,
    config: {
      start_date: config.startDate,
      cost_date: config.costDate,
      capital_by_market: config.capitalByMarket,
    },
    candidates: (analysis.candidates ?? []).map((row) => ({
      ticker: row.ticker,
      name: row.name,
      name_zh: row.name_zh,
      name_en: row.name_en,
      market: row.market,
      price: row.price,
      change_percent: row.change_percent,
      market_cap: row.market_cap,
      pe: row.pe ?? null,
      pb: row.pb ?? null,
      dividend_yield: row.dividend_yield ?? null,
      eps: row.eps ?? null,
      turn_rate: row.turn_rate ?? null,
      sector_l1: row.sector_l1,
      sector_l2: row.sector_l2,
      sector_l3: row.sector_l3,
    })),
    holdings: analysis.holdings.map((row) => ({
      ticker: row.ticker,
      name: row.name,
      name_zh: row.name_zh,
      name_en: row.name_en,
      market: row.market,
      shares: row.shares,
      weight: row.weight,
      cost: row.cost,
      cost_low: row.cost_low ?? null,
      cost_high: row.cost_high ?? null,
      uses_default_cost: row.uses_default_cost ?? true,
      cost_date: row.cost_date ?? null,
      open_date: row.open_date ?? null,
      uses_default_open_date: row.uses_default_open_date ?? true,
      cost_basis: row.cost_basis ?? row.cost * row.shares,
      price: row.price,
      change_percent: row.change_percent,
      total_return_pct: row.total_return_pct ?? null,
      sector: row.sector_l3 || row.sector_l1,
      sector_l1: row.sector_l1,
      sector_l2: row.sector_l2,
      sector_l3: row.sector_l3,
      market_value: row.market_value,
    })),
    kpis: analysis.kpis,
    performance: includePerformance
      ? {
          window_start: analysis.performance_window_start ?? null,
          window_end: analysis.performance_window_end ?? null,
          series_by_market: analysis.nav_by_market,
          candidate_series_by_market: analysis.candidate_nav_by_market,
          benchmark_by_market: analysis.benchmark_by_market,
          benchmark_symbol_by_market: analysis.benchmark_symbol_by_market,
          stats_by_market: analysis.stats_by_market,
          candidate_stats_by_market: analysis.candidate_stats_by_market,
        }
      : null,
    net_value_by_market: analysis.net_value_by_market,
    cost_basis_by_market: analysis.cost_basis_by_market,
    orders: (analysis.orders ?? []).map((row) => ({
      id: row.id,
      ticker: row.ticker,
      name: row.name,
      name_zh: row.name_zh,
      name_en: row.name_en,
      market: row.market,
      order_side: row.order_side,
      order_status: row.order_status,
      price: row.price,
      qty: row.qty,
      order_time: row.order_time ?? null,
      fill_time: row.fill_time ?? null,
      fill_price: row.fill_price ?? null,
      created_at: row.created_at,
    })),
  };
}

async function fetchPortfolioList(query?: string): Promise<PortfolioListResponse> {
  const params = query ? new URLSearchParams({ query }) : '';
  const suffix = params ? `?${params}` : '';
  return fetchJson<PortfolioListResponse>(`${API_PREFIX}/portfolio${suffix}`);
}

async function fetchPortfolioSummary(portfolioId: string): Promise<FolioPortfolioSummaryResponse | undefined> {
  const list = await fetchPortfolioList();
  return list.items.find((item) => item.id === portfolioId);
}

export async function fetchFolioPortfolios(): Promise<FolioPortfolioSummaryResponse[]> {
  const list = await fetchPortfolioList();
  return list.items;
}

export async function searchFolioPortfolios(query: string): Promise<FolioPortfolioSearchHit[]> {
  const list = await fetchPortfolioList(query);
  return mapApiSearchHits(
    list.items.map((item) => ({
      id: item.id,
      match_type: 'name' as const,
      matched_name: item.name,
    })),
  );
}

export async function fetchFolioPortfolioDetail(
  portfolioId: string,
  options?: { benchmark?: string | null; includePerformance?: boolean; startDate?: string | null },
): Promise<FolioPortfolioDetail> {
  const params = new URLSearchParams();
  if (options?.benchmark) params.set('benchmark', options.benchmark);
  if (options?.includePerformance === false) params.set('include_performance', 'false');
  if (options?.startDate) params.set('start_date', options.startDate);
  const query = params.toString();
  const [analysis, summary] = await Promise.all([
    fetchJson<PortfolioAnalysisResponse>(
      `${API_PREFIX}/portfolio/${encodeURIComponent(portfolioId)}/analysis${query ? `?${query}` : ''}`,
    ),
    fetchPortfolioSummary(portfolioId),
  ]);
  return mapFolioPortfolioDetail(
    mapAnalysisToDetail(analysis, summary, options?.includePerformance !== false),
  );
}

export async function createFolioPortfolio(name: string): Promise<FolioPortfolioDetail> {
  const analysis = await fetchJson<PortfolioAnalysisResponse>(`${API_PREFIX}/portfolio/manage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action: 'create', name }),
  });
  return mapFolioPortfolioDetail(mapAnalysisToDetail(analysis));
}

export async function updateFolioPortfolio(
  portfolioId: string,
  payload: {
    name?: string;
    kind?: 'manual' | 'agent';
    pinned?: boolean;
    config?: FolioPortfolioConfig;
    shares_by_ticker?: Record<string, number>;
    shares_locked_by_ticker?: Record<string, boolean>;
    manual_shares_by_ticker?: Record<string, boolean>;
    open_date_by_ticker?: Record<string, string | null>;
    open_date_locked_by_ticker?: Record<string, boolean>;
    cost_by_ticker?: Record<string, number | null>;
    cost_locked_by_ticker?: Record<string, boolean>;
  },
): Promise<FolioPortfolioDetail> {
  if (
    payload.name !== undefined ||
    payload.pinned !== undefined ||
    payload.config !== undefined ||
    payload.kind !== undefined
  ) {
    await fetchJson<PortfolioAnalysisResponse>(`${API_PREFIX}/portfolio/manage`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        action: 'update',
        portfolio_id: portfolioId,
        name: payload.name,
        kind: payload.kind,
        pinned: payload.pinned,
        start_date: payload.config?.startDate,
        capital_by_market: payload.config?.capitalByMarket,
      }),
    });
  }

  void payload.shares_locked_by_ticker;
  void payload.manual_shares_by_ticker;
  void payload.open_date_locked_by_ticker;
  void payload.cost_by_ticker;
  void payload.cost_locked_by_ticker;

  if (payload.open_date_by_ticker || payload.shares_by_ticker) {
    const analysis = await fetchJson<PortfolioAnalysisResponse>(
      `${API_PREFIX}/portfolio/holdings/metadata`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          portfolio_id: portfolioId,
          open_date_by_ticker: payload.open_date_by_ticker,
          shares_by_ticker: payload.shares_by_ticker,
        }),
      },
    );
    const summary = await fetchPortfolioSummary(portfolioId);
    return mapFolioPortfolioDetail(mapAnalysisToDetail(analysis, summary, true));
  }

  return fetchFolioPortfolioDetail(portfolioId, {
    includePerformance: true,
    startDate: payload.config?.startDate,
  });
}

export async function deleteFolioPortfolio(portfolioId: string): Promise<void> {
  await fetchJson<PortfolioAnalysisResponse>(`${API_PREFIX}/portfolio/manage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action: 'delete', portfolio_id: portfolioId }),
  });
}

export async function addFolioHolding(
  portfolioId: string,
  payload: { ticker: string; market?: MarketCode; shares?: number },
): Promise<FolioPortfolioDetail> {
  const analysis = await fetchJson<PortfolioAnalysisResponse>(`${API_PREFIX}/portfolio/holdings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      portfolio_id: portfolioId,
      holding_details: {
        ticker: payload.ticker,
        market: payload.market === 'cn' ? 'sh' : payload.market,
        shares: payload.shares,
      },
    }),
  });
  const summary = await fetchPortfolioSummary(portfolioId);
  return mapFolioPortfolioDetail(mapAnalysisToDetail(analysis, summary, true));
}

export async function removeFolioHolding(
  portfolioId: string,
  payload: { ticker: string; market: MarketCode },
): Promise<FolioPortfolioDetail> {
  const analysis = await fetchJson<PortfolioAnalysisResponse>(`${API_PREFIX}/portfolio/holdings`, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      portfolio_id: portfolioId,
      ticker: payload.ticker,
      market: payload.market === 'cn' ? 'sh' : payload.market,
    }),
  });
  const summary = await fetchPortfolioSummary(portfolioId);
  return mapFolioPortfolioDetail(mapAnalysisToDetail(analysis, summary, true));
}

export async function createFolioOrder(
  portfolioId: string,
  payload: FolioCreateOrderPayload,
): Promise<FolioPortfolioDetail> {
  const analysis = await fetchJson<PortfolioAnalysisResponse>(`${API_PREFIX}/portfolio/orders`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      portfolio_id: portfolioId,
      ticker: payload.ticker,
      market: payload.market === 'cn' ? 'sh' : payload.market,
      order_side: payload.orderSide,
      price: payload.price,
      qty: payload.qty,
      order_time: payload.orderTime ?? undefined,
    }),
  });
  const summary = await fetchPortfolioSummary(portfolioId);
  return mapFolioPortfolioDetail(mapAnalysisToDetail(analysis, summary, true));
}

export async function autoAllocateFolioPortfolio(
  portfolioId: string,
  market?: MarketCode,
  allocationStrategy: FolioAllocationStrategy = 'market_cap',
): Promise<FolioPortfolioDetail> {
  const analysis = await fetchJson<PortfolioAnalysisResponse>(`${API_PREFIX}/portfolio/allocate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      portfolio_id: portfolioId,
      market,
      allocation_strategy: allocationStrategy,
    }),
  });
  const summary = await fetchPortfolioSummary(portfolioId);
  return mapFolioPortfolioDetail(mapAnalysisToDetail(analysis, summary, true));
}

export { ApiError };
