import { fetchJson } from './http';
import {
  fetchMockCoreTickerEvents,
  fetchMockCoreTickerFinIndicators,
  fetchMockCoreTickerIncome,
  fetchMockCoreTickerKline,
  fetchMockCoreTickerNews,
  fetchMockCoreTickerPeBand,
  fetchMockCoreTickerQuote,
  fetchMockCoreTickerSearch,
  fetchMockCoreTickerSector,
  USE_INTERACTIVE_MOCKS,
} from '../mocks/interactiveMockData';
import type { MarketCode } from '../types/dojoMesh';
import type {
  CorePeBandPoint,
  CoreSectorLabelPath,
  CoreSectorOption,
  CoreTickerFinIndicatorsResponse,
  CoreTickerEventsResponse,
  CoreTickerIncomeResponse,
  CoreTickerNewsResponse,
  CoreIncomeDistributionItem,
  CoreIncomeDistributionSlice,
  CoreIncomeMainopType,
  CoreTickerSearchItem,
  StockEventRow,
  StockFinIndicatorRow,
  StockNewsRow,
} from '../types/dojoCore';
import type { SectorPathSelection } from '../types/sectorTaxonomy';

const API_PREFIX = '/api/v1';

export interface CoreTickerSectorResponse {
  ticker: string;
  market: MarketCode;
  sector_options: CoreSectorOption[];
}

function mapLabelPath(raw: {
  level_1: { zh: string; en: string };
  level_2: { zh: string; en: string };
  level_3: { zh: string; en: string };
}): CoreSectorLabelPath {
  return {
    level1: raw.level_1,
    level2: raw.level_2,
    level3: raw.level_3,
  };
}

function mapSectorOption(raw: {
  role: 'primary' | 'secondary';
  level1_id: string;
  level2_id: string;
  level3_id: string;
  label: {
    level_1: { zh: string; en: string };
    level_2: { zh: string; en: string };
    level_3: { zh: string; en: string };
  };
}): CoreSectorOption {
  return {
    role: raw.role,
    level1Id: raw.level1_id,
    level2Id: raw.level2_id,
    level3Id: raw.level3_id,
    label: mapLabelPath(raw.label),
  };
}

export async function fetchCoreTickerSector(params: {
  ticker: string;
  market?: MarketCode;
}): Promise<CoreTickerSectorResponse> {
  if (USE_INTERACTIVE_MOCKS) return fetchMockCoreTickerSector(params);
  const query = new URLSearchParams({ ticker: params.ticker });
  if (params.market) query.set('market', params.market);
  const raw = await fetchJson<{
    ticker: string;
    market: MarketCode;
    sector_options: Array<{
      role: 'primary' | 'secondary';
      level1_id: string;
      level2_id: string;
      level3_id: string;
      label: {
        level_1: { zh: string; en: string };
        level_2: { zh: string; en: string };
        level_3: { zh: string; en: string };
      };
    }>;
  }>(`${API_PREFIX}/dojo-core/ticker/sector?${query}`);
  return {
    ticker: raw.ticker,
    market: raw.market,
    sector_options: raw.sector_options.map(mapSectorOption),
  };
}

export async function fetchCoreTickerSearch(params: {
  q: string;
  market?: MarketCode;
  selection?: SectorPathSelection | null;
  limit?: number;
}): Promise<CoreTickerSearchItem[]> {
  if (USE_INTERACTIVE_MOCKS) return fetchMockCoreTickerSearch(params);
  const query = new URLSearchParams({ q: params.q });
  if (params.market) query.set('market', params.market);
  if (params.selection?.level1Id) query.set('level1_id', params.selection.level1Id);
  if (params.selection?.level2Id) query.set('level2_id', params.selection.level2Id);
  if (params.selection?.level3Id) query.set('level3_id', params.selection.level3Id);
  if (params.limit != null) query.set('limit', String(params.limit));
  const raw = await fetchJson<{
    query: string;
    items: Array<{
      ticker: string;
      market: MarketCode;
      name: { zh: string; en: string };
      market_cap: number;
    }>;
  }>(`${API_PREFIX}/dojo-core/tickers/search?${query}`);
  return raw.items.map((item) => ({
    ticker: item.ticker,
    market: item.market,
    name: item.name,
    market_cap: item.market_cap,
  }));
}

function optionalNumber(raw: Record<string, unknown>, key: string): number | null {
  const value = raw[key];
  return value != null ? Number(value) : null;
}

function mapFinIndicatorRow(raw: Record<string, unknown>): StockFinIndicatorRow {
  return {
    symbol: String(raw.symbol ?? ''),
    report_date: raw.report_date != null ? String(raw.report_date) : null,
    std_report_date: raw.std_report_date != null ? String(raw.std_report_date) : null,
    report_type: raw.report_type != null ? String(raw.report_type) : null,
    report_period_name: raw.report_period_name != null ? String(raw.report_period_name) : null,
    season_label: raw.season_label != null ? String(raw.season_label) : null,
    total_operating_revenue: optionalNumber(raw, 'total_operating_revenue'),
    total_operating_rev_yoy: optionalNumber(raw, 'total_operating_rev_yoy'),
    net_profit_attr_parent: optionalNumber(raw, 'net_profit_attr_parent'),
    gross_margin: optionalNumber(raw, 'gross_margin'),
    net_margin: optionalNumber(raw, 'net_margin'),
    roe_weighted: optionalNumber(raw, 'roe_weighted'),
    roa: optionalNumber(raw, 'roa'),
    eps_basic: optionalNumber(raw, 'eps_basic'),
    eps_ttm: optionalNumber(raw, 'eps_ttm'),
    pe_ttm: optionalNumber(raw, 'pe_ttm'),
    pb_ttm: optionalNumber(raw, 'pb_ttm'),
    bps: optionalNumber(raw, 'bps'),
    dividend_rate: optionalNumber(raw, 'dividend_rate'),
    divi_ratio: optionalNumber(raw, 'divi_ratio'),
    total_market_cap: optionalNumber(raw, 'total_market_cap'),
    hksk_market_cap: optionalNumber(raw, 'hksk_market_cap'),
  };
}

export async function fetchCoreTickerFinIndicators(params: {
  ticker: string;
  market?: MarketCode;
  limit?: number;
}): Promise<CoreTickerFinIndicatorsResponse> {
  if (USE_INTERACTIVE_MOCKS) return fetchMockCoreTickerFinIndicators(params);
  const query = new URLSearchParams({ ticker: params.ticker });
  if (params.market) query.set('market', params.market);
  if (params.limit != null) query.set('limit', String(params.limit));
  const raw = await fetchJson<{
    ticker: string;
    market: MarketCode;
    report_type: string;
    as_of: string | null;
    source: 'local' | 'remote';
    items: Record<string, unknown>[];
  }>(`${API_PREFIX}/dojo-core/ticker/fin-indicators?${query}`);
  return {
    ticker: raw.ticker,
    market: raw.market,
    report_type: raw.report_type,
    as_of: raw.as_of,
    source: raw.source,
    items: raw.items.map(mapFinIndicatorRow),
  };
}

function mapStockEventRow(raw: Record<string, unknown>): StockEventRow {
  const optionalString = (key: string): string | null => {
    const value = raw[key];
    return value != null ? String(value) : null;
  };
  return {
    id: optionalString('id'),
    symbol: optionalString('symbol'),
    event_date: optionalString('event_date'),
    remind_date: optionalString('remind_date'),
    notice_date: optionalString('notice_date'),
    event_type: optionalString('event_type'),
    specific_eventtype: optionalString('specific_eventtype'),
    type_name: optionalString('type_name'),
    event_type_name: optionalString('event_type_name'),
    level1_content: optionalString('level1_content'),
    level2_content: optionalString('level2_content'),
    title: optionalString('title'),
    content: optionalString('content'),
    event_content: optionalString('event_content'),
  };
}

export async function fetchCoreTickerEvents(params: {
  ticker: string;
  market?: MarketCode;
  page_size?: number;
}): Promise<CoreTickerEventsResponse> {
  if (USE_INTERACTIVE_MOCKS) return fetchMockCoreTickerEvents(params);
  const query = new URLSearchParams({ ticker: params.ticker });
  if (params.market) query.set('market', params.market);
  if (params.page_size != null) query.set('page_size', String(params.page_size));
  const raw = await fetchJson<{
    ticker: string;
    market: MarketCode;
    as_of: string | null;
    source: 'local' | 'remote';
    items: Record<string, unknown>[];
  }>(`${API_PREFIX}/dojo-core/ticker/events?${query}`);
  return {
    ticker: raw.ticker,
    market: raw.market,
    as_of: raw.as_of,
    source: raw.source,
    items: raw.items.map(mapStockEventRow),
  };
}

function mapStockNewsRow(raw: Record<string, unknown>): StockNewsRow {
  const optionalString = (key: string): string | null => {
    const value = raw[key];
    return value != null ? String(value) : null;
  };
  return {
    id: optionalString('id'),
    publish_date: optionalString('publish_date'),
    title: optionalString('title'),
    url: optionalString('url'),
    description: optionalString('description'),
    source: optionalString('source'),
  };
}

export async function fetchCoreTickerNews(params: {
  ticker: string;
  market?: MarketCode;
  page_size?: number;
}): Promise<CoreTickerNewsResponse> {
  if (USE_INTERACTIVE_MOCKS) return fetchMockCoreTickerNews(params);
  const query = new URLSearchParams({ ticker: params.ticker });
  if (params.market) query.set('market', params.market);
  if (params.page_size != null) query.set('page_size', String(params.page_size));
  const raw = await fetchJson<{
    ticker: string;
    market: MarketCode;
    as_of: string | null;
    source: 'local' | 'remote';
    items: Record<string, unknown>[];
  }>(`${API_PREFIX}/dojo-core/ticker/news?${query}`);
  return {
    ticker: raw.ticker,
    market: raw.market,
    as_of: raw.as_of,
    source: raw.source,
    items: raw.items.map(mapStockNewsRow),
  };
}

export interface CoreTickerKlineBar {
  symbol: string;
  kline_t: string;
  bar_time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  vol: number;
  amount: number;
}

export interface CoreTickerKlineResponse {
  symbol: string;
  as_of: string | null;
  bars: CoreTickerKlineBar[];
}

export interface CoreTickerQuoteResponse {
  ticker: string;
  market: MarketCode;
  currency?: string | null;
  last_price: number;
  change: number;
  change_percent: number;
  pre_close: number;
  open: number;
  high: number;
  low: number;
  volume: number;
  amount?: number | null;
  total_shares?: number | null;
  market_cap: number;
  pe: number;
  forward_pe?: number | null;
  pb: number;
  turn_rate: number;
  exchange_name?: string | null;
  industry?: string | null;
  sector?: string | null;
  country?: string | null;
}

export async function fetchCoreTickerQuote(params: {
  ticker: string;
  market?: MarketCode;
}): Promise<CoreTickerQuoteResponse> {
  if (USE_INTERACTIVE_MOCKS) return fetchMockCoreTickerQuote(params);
  const query = new URLSearchParams({ ticker: params.ticker });
  if (params.market) query.set('market', params.market);
  const raw = await fetchJson<{
    ticker: string;
    market: MarketCode;
    currency?: string | null;
    last_price: number;
    change: number;
    change_percent: number;
    pre_close: number;
    open: number;
    high: number;
    low: number;
    volume: number;
    amount?: number | null;
    total_shares?: number | null;
    market_cap: number;
    pe: number;
    forward_pe?: number | null;
    pb: number;
    turn_rate: number;
    exchange_name?: string | null;
    industry?: string | null;
    sector?: string | null;
    country?: string | null;
  }>(`${API_PREFIX}/dojo-core/ticker/quote?${query}`);
  return {
    ticker: raw.ticker,
    market: raw.market,
    currency: raw.currency,
    last_price: raw.last_price,
    change: raw.change,
    change_percent: raw.change_percent,
    pre_close: raw.pre_close,
    open: raw.open,
    high: raw.high,
    low: raw.low,
    volume: raw.volume,
    amount: raw.amount,
    total_shares: raw.total_shares,
    market_cap: raw.market_cap,
    pe: raw.pe,
    forward_pe: raw.forward_pe,
    pb: raw.pb,
    turn_rate: raw.turn_rate,
    exchange_name: raw.exchange_name,
    industry: raw.industry,
    sector: raw.sector,
    country: raw.country,
  };
}

export interface CoreTickerPeBandResponse {
  ticker: string;
  market: MarketCode;
  as_of: string | null;
  total_shares: number;
  points: CorePeBandPoint[];
}

export async function fetchCoreTickerPeBand(params: {
  ticker: string;
  market?: MarketCode;
  limit?: number;
}): Promise<CoreTickerPeBandResponse> {
  if (USE_INTERACTIVE_MOCKS) return fetchMockCoreTickerPeBand(params);
  const query = new URLSearchParams({ ticker: params.ticker });
  if (params.market) query.set('market', params.market);
  if (params.limit != null) query.set('limit', String(params.limit));
  const raw = await fetchJson<{
    ticker: string;
    market: MarketCode;
    as_of: string | null;
    total_shares: number;
    points: Array<{
      date: string;
      pe: number;
      mean: number;
      upper1: number;
      lower1: number;
      upper2: number;
      lower2: number;
    }>;
  }>(`${API_PREFIX}/dojo-core/ticker/pe-band?${query}`);
  return {
    ticker: raw.ticker,
    market: raw.market,
    as_of: raw.as_of,
    total_shares: raw.total_shares,
    points: raw.points.map((point) => ({
      date: point.date,
      pe: point.pe,
      mean: point.mean,
      upper1: point.upper1,
      lower1: point.lower1,
      upper2: point.upper2,
      lower2: point.lower2,
    })),
  };
}

export async function fetchCoreTickerKline(params: {
  ticker: string;
  market?: MarketCode;
  kline_t?: string;
  limit?: number;
}): Promise<CoreTickerKlineResponse> {
  if (USE_INTERACTIVE_MOCKS) return fetchMockCoreTickerKline(params);
  const query = new URLSearchParams({ ticker: params.ticker });
  if (params.market) query.set('market', params.market);
  if (params.kline_t) query.set('kline_t', params.kline_t);
  if (params.limit != null) query.set('limit', String(params.limit));
  const raw = await fetchJson<{
    symbol: string;
    as_of: string | null;
    bars: Array<{
      symbol: string;
      kline_t: string;
      bar_time: string;
      open: number;
      high: number;
      low: number;
      close: number;
      vol: number;
      amount: number;
    }>;
  }>(`${API_PREFIX}/dojo-core/ticker/kline?${query}`);
  return {
    symbol: raw.symbol,
    as_of: raw.as_of,
    bars: raw.bars.map((bar) => ({
      symbol: bar.symbol,
      kline_t: bar.kline_t,
      bar_time: bar.bar_time,
      open: bar.open,
      high: bar.high,
      low: bar.low,
      close: bar.close,
      vol: bar.vol,
      amount: bar.amount ?? 0,
    })),
  };
}

function mapIncomeDistributionItem(raw: Record<string, unknown>): CoreIncomeDistributionItem {
  return {
    item_name: String(raw.item_name ?? ''),
    main_business_income: Number(raw.main_business_income ?? 0),
    mbi_ratio: Number(raw.mbi_ratio ?? 0),
  };
}

function mapIncomeDistributionSlice(raw: Record<string, unknown>): CoreIncomeDistributionSlice {
  const mainopType = String(raw.mainop_type ?? '') as CoreIncomeMainopType;
  const items = Array.isArray(raw.items)
    ? raw.items.map((item) => mapIncomeDistributionItem(item as Record<string, unknown>))
    : [];
  return {
    mainop_type: mainopType,
    report_date: raw.report_date != null ? String(raw.report_date) : null,
    items,
  };
}

export async function fetchCoreTickerIncome(params: {
  ticker: string;
  market?: MarketCode;
}): Promise<CoreTickerIncomeResponse> {
  if (USE_INTERACTIVE_MOCKS) return fetchMockCoreTickerIncome(params);
  const query = new URLSearchParams({ ticker: params.ticker });
  if (params.market) query.set('market', params.market);
  const raw = await fetchJson<{
    ticker: string;
    market: MarketCode;
    report_date: string | null;
    distributions: Record<string, unknown>[];
  }>(`${API_PREFIX}/dojo-core/ticker/income?${query}`);
  return {
    ticker: raw.ticker,
    market: raw.market,
    report_date: raw.report_date,
    distributions: raw.distributions.map(mapIncomeDistributionSlice),
  };
}
