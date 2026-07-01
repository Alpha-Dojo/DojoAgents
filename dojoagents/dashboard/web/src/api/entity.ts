import { fetchJson } from './http';
import { dedupeFetch } from './adapters/cache';
import type { MarketCode } from '../types/market';
import type {
  EntityPeBandPoint,
  EntitySectorLabelPath,
  EntitySectorOption,
  EntityTickerFinIndicatorsResponse,
  EntityTickerEventsResponse,
  EntityTickerIncomeResponse,
  EntityTickerNewsResponse,
  EntityIncomeDistributionItem,
  EntityIncomeDistributionSlice,
  EntityIncomeMainopType,
  EntityTickerSearchItem,
  StockEventRow,
  StockFinIndicatorRow,
  StockNewsRow,
} from '../types/entity';
import type { SectorPathSelection } from '../types/sectorTaxonomy';
import { REVENUE_CHART_YOY_BASELINE_START } from '../utils/entityFinIndicators';

const API_PREFIX = '/api/v1';

const INCOME_DIMENSION_TO_MAINOP: Record<string, EntityIncomeMainopType> = {
  industry: '1',
  product: '2',
  region: '3',
};

export interface CoreTickerSectorResponse {
  ticker: string;
  market: MarketCode;
  sector_options: EntitySectorOption[];
}

function mapLabelPath(raw: {
  level_1: { zh: string; en: string };
  level_2: { zh: string; en: string };
  level_3: { zh: string; en: string };
}): EntitySectorLabelPath {
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
}): EntitySectorOption {
  return {
    role: raw.role,
    level1Id: raw.level1_id,
    level2Id: raw.level2_id,
    level3Id: raw.level3_id,
    label: mapLabelPath(raw.label),
  };
}

function mapSectorOptionFromQuotePath(raw: {
  role: 'primary' | 'secondary';
  level1_id: string;
  level2_id: string;
  level3_id: string;
  labels: Record<string, { zh: string; en: string }>;
}): EntitySectorOption {
  return {
    role: raw.role,
    level1Id: raw.level1_id,
    level2Id: raw.level2_id,
    level3Id: raw.level3_id,
    label: {
      level1: raw.labels.L1 ?? raw.labels.level_1 ?? { zh: '', en: '' },
      level2: raw.labels.L2 ?? raw.labels.level_2 ?? { zh: '', en: '' },
      level3: raw.labels.L3 ?? raw.labels.level_3 ?? { zh: '', en: '' },
    },
  };
}

interface TickerFinancialsBundle {
  ticker: string;
  market: MarketCode;
  report_type: string | null;
  as_of: string | null;
  indicators: Record<string, unknown>[];
  income_distributions: Array<{
    dimension: string;
    report_date: string | null;
    items: Record<string, unknown>[];
  }>;
}

interface TickerNewsEventsBundle {
  ticker: string;
  market: MarketCode;
  news: Array<{
    title: string;
    summary: string;
    published_at: string | null;
    source: string | null;
    url: string | null;
  }>;
  events: Array<{
    event_type: string;
    title: string;
    event_date: string | null;
    description: string;
  }>;
}

interface TickerPriceTrendsBundle {
  ticker: string;
  market: MarketCode;
  interval: string;
  as_of: string | null;
  klines: Array<{
    datetime: string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume?: number | null;
  }>;
  pe_band: EntityPeBandPoint[];
}

function quoteKey(ticker: string, market?: MarketCode) {
  return `quote:${market ?? ''}:${ticker}`;
}

function financialsKey(
  ticker: string,
  market?: MarketCode,
  startDate?: string,
  endDate?: string,
) {
  return `fin:v3:${market ?? ''}:${ticker}:${startDate ?? ''}:${endDate ?? ''}`;
}

function canonicalFinancialsKey(ticker: string, market?: MarketCode) {
  const endDate = new Date().toISOString().slice(0, 10);
  return financialsKey(ticker, market, REVENUE_CHART_YOY_BASELINE_START, endDate);
}

function newsEventsKey(ticker: string, market?: MarketCode, pageSize?: number) {
  return `news:${market ?? ''}:${ticker}:${pageSize ?? 20}`;
}

function priceTrendsKey(
  ticker: string,
  market?: MarketCode,
  startDate?: string,
  endDate?: string,
) {
  return `price:v2:${market ?? ''}:${ticker}:${startDate ?? ''}:${endDate ?? ''}`;
}

function fetchFinancialsBundle(params: {
  ticker: string;
  market?: MarketCode;
  limit?: number;
  start_date?: string;
  end_date?: string;
}): Promise<TickerFinancialsBundle> {
  const query = new URLSearchParams({ ticker: params.ticker });
  if (params.market) query.set('market', params.market);
  if (params.start_date) query.set('start_date', params.start_date);
  if (params.end_date) query.set('end_date', params.end_date);
  if (params.limit != null && !params.start_date) query.set('limit', String(params.limit));
  return dedupeFetch(
    financialsKey(params.ticker, params.market, params.start_date, params.end_date),
    () => fetchJson<TickerFinancialsBundle>(`${API_PREFIX}/ticker/financials?${query}`),
  );
}

function fetchNewsEventsBundle(params: {
  ticker: string;
  market?: MarketCode;
  page_size?: number;
}): Promise<TickerNewsEventsBundle> {
  const query = new URLSearchParams({ ticker: params.ticker });
  if (params.market) query.set('market', params.market);
  if (params.page_size != null) query.set('page_size', String(params.page_size));
  return dedupeFetch(newsEventsKey(params.ticker, params.market, params.page_size), () =>
    fetchJson<TickerNewsEventsBundle>(`${API_PREFIX}/ticker/news-events?${query}`),
  );
}

function fetchPriceTrendsBundle(params: {
  ticker: string;
  market?: MarketCode;
  start_date?: string;
  end_date?: string;
  limit?: number;
}): Promise<TickerPriceTrendsBundle> {
  const query = new URLSearchParams({ ticker: params.ticker });
  if (params.market) query.set('market', params.market);
  if (params.start_date && params.end_date) {
    query.set('start_date', params.start_date);
    query.set('end_date', params.end_date);
  } else if (params.limit != null) {
    query.set('limit', String(params.limit));
  }
  return dedupeFetch(
    priceTrendsKey(params.ticker, params.market, params.start_date, params.end_date),
    () => fetchJson<TickerPriceTrendsBundle>(`${API_PREFIX}/ticker/price-trends?${query}`),
  );
}

interface TickerQuoteApiResponse extends CoreTickerQuoteResponse {
  sector_paths?: Array<{
    role: 'primary' | 'secondary';
    level1_id: string;
    level2_id: string;
    level3_id: string;
    labels: Record<string, { zh: string; en: string }>;
  }>;
}

async function fetchTickerQuoteRaw(params: {
  ticker: string;
  market?: MarketCode;
}): Promise<TickerQuoteApiResponse> {
  const query = new URLSearchParams({ ticker: params.ticker });
  if (params.market) query.set('market', params.market);
  return dedupeFetch(quoteKey(params.ticker, params.market), () =>
    fetchJson<TickerQuoteApiResponse>(`${API_PREFIX}/ticker/quote?${query}`),
  );
}

export async function fetchCoreTickerSector(params: {
  ticker: string;
  market?: MarketCode;
}): Promise<CoreTickerSectorResponse> {
  const raw = await fetchTickerQuoteRaw(params);
  return {
    ticker: raw.ticker,
    market: raw.market,
    sector_options: (raw.sector_paths ?? []).map(mapSectorOptionFromQuotePath),
  };
}

export async function fetchEntityTickerSearch(params: {
  q: string;
  market?: MarketCode;
  selection?: SectorPathSelection | null;
  limit?: number;
}): Promise<EntityTickerSearchItem[]> {
  void params.selection;
  const query = new URLSearchParams({ q: params.q });
  if (params.market) query.set('market', params.market);
  if (params.limit != null) query.set('limit', String(params.limit));
  const raw = await fetchJson<{
    query: string;
    items: Array<{
      ticker: string;
      market: MarketCode;
      name: { zh: string; en: string };
      market_cap: number;
    }>;
  }>(`${API_PREFIX}/utility/search/company-ticker?${query}`);
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

function optionalNumberFirst(raw: Record<string, unknown>, ...keys: string[]): number | null {
  for (const key of keys) {
    const value = raw[key];
    if (value == null || value === '') continue;
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return null;
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
    gross_margin: optionalNumberFirst(raw, 'gross_margin', 'gross_profit_ratio'),
    net_margin: optionalNumberFirst(raw, 'net_margin', 'net_profit_ratio'),
    roe_weighted: optionalNumberFirst(raw, 'roe_weighted', 'roe_diluted', 'roe'),
    roa: optionalNumberFirst(raw, 'roa', 'jroa'),
    eps_basic: optionalNumber(raw, 'eps_basic'),
    eps_ttm: optionalNumber(raw, 'eps_ttm'),
    pe_ttm: optionalNumber(raw, 'pe_ttm'),
    pb_ttm: optionalNumber(raw, 'pb_ttm'),
    bps: optionalNumber(raw, 'bps'),
    dividend_rate: optionalNumber(raw, 'dividend_rate'),
    divi_ratio: optionalNumber(raw, 'divi_ratio'),
    total_market_cap: optionalNumber(raw, 'total_market_cap'),
    hksk_market_cap: optionalNumber(raw, 'hksk_market_cap'),
    calendar_year: optionalNumber(raw, 'calendar_year'),
    calendar_quarter: optionalNumber(raw, 'calendar_quarter'),
    calendar_period_label:
      raw.calendar_period_label != null ? String(raw.calendar_period_label) : null,
    calendar_period_index: optionalNumber(raw, 'calendar_period_index'),
  };
}

async function fetchCanonicalFinancialsBundle(params: {
  ticker: string;
  market?: MarketCode;
}): Promise<TickerFinancialsBundle> {
  const endDate = new Date().toISOString().slice(0, 10);
  return dedupeFetch(canonicalFinancialsKey(params.ticker, params.market), () =>
    fetchFinancialsBundle({
      ticker: params.ticker,
      market: params.market,
      start_date: REVENUE_CHART_YOY_BASELINE_START,
      end_date: endDate,
    }),
  );
}

export async function fetchCoreTickerFinIndicators(params: {
  ticker: string;
  market?: MarketCode;
  startDate?: string;
  endDate?: string;
}): Promise<EntityTickerFinIndicatorsResponse> {
  const raw = await fetchCanonicalFinancialsBundle(params);
  return {
    ticker: raw.ticker,
    market: raw.market,
    report_type: raw.report_type ?? '',
    as_of: raw.as_of,
    source: 'local',
    items: raw.indicators.map(mapFinIndicatorRow),
  };
}

function mapStockEventRow(raw: {
  event_type: string;
  title: string;
  event_date: string | null;
  description: string;
}): StockEventRow {
  return {
    id: null,
    symbol: null,
    event_date: raw.event_date,
    remind_date: null,
    notice_date: raw.event_date,
    event_type: raw.event_type,
    specific_eventtype: raw.title || null,
    type_name: raw.event_type || null,
    event_type_name: raw.event_type || null,
    level1_content: raw.description || null,
    level2_content: null,
    title: raw.title,
    content: raw.description,
    event_content: raw.description,
  };
}

export async function fetchCoreTickerEvents(params: {
  ticker: string;
  market?: MarketCode;
  page_size?: number;
}): Promise<EntityTickerEventsResponse> {
  const raw = await fetchNewsEventsBundle(params);
  return {
    ticker: raw.ticker,
    market: raw.market,
    as_of: null,
    source: 'local',
    items: raw.events.map(mapStockEventRow),
  };
}

function mapStockNewsRow(raw: {
  title: string;
  summary: string;
  published_at: string | null;
  source: string | null;
  url: string | null;
}): StockNewsRow {
  return {
    id: null,
    publish_date: raw.published_at,
    title: raw.title,
    url: raw.url,
    description: raw.summary,
    source: raw.source,
  };
}

export async function fetchCoreTickerNews(params: {
  ticker: string;
  market?: MarketCode;
  page_size?: number;
}): Promise<EntityTickerNewsResponse> {
  const raw = await fetchNewsEventsBundle(params);
  return {
    ticker: raw.ticker,
    market: raw.market,
    as_of: null,
    source: 'local',
    items: raw.news.map(mapStockNewsRow),
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
  name?: { zh: string; en: string };
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
  dividend_yield?: number | null;
  exchange_name?: string | null;
  industry?: string | null;
  sector?: string | null;
  country?: string | null;
}

export async function fetchCoreTickerQuote(params: {
  ticker: string;
  market?: MarketCode;
}): Promise<CoreTickerQuoteResponse> {
  return fetchTickerQuoteRaw(params);
}

export interface CoreTickerPeBandResponse {
  ticker: string;
  market: MarketCode;
  as_of: string | null;
  total_shares: number;
  points: EntityPeBandPoint[];
}

export async function fetchCoreTickerPeBand(params: {
  ticker: string;
  market?: MarketCode;
  start_date?: string;
  end_date?: string;
  limit?: number;
}): Promise<CoreTickerPeBandResponse> {
  const raw = await fetchPriceTrendsBundle(params);
  let totalShares = 0;
  try {
    const quote = await fetchCoreTickerQuote({
      ticker: params.ticker,
      market: params.market,
    });
    totalShares = quote.total_shares ?? 0;
  } catch {
    totalShares = 0;
  }
  return {
    ticker: raw.ticker,
    market: raw.market,
    as_of: raw.as_of,
    total_shares: totalShares,
    points: raw.pe_band,
  };
}

export async function fetchCoreTickerKline(params: {
  ticker: string;
  market?: MarketCode;
  kline_t?: string;
  start_date?: string;
  end_date?: string;
  limit?: number;
}): Promise<CoreTickerKlineResponse> {
  void params.kline_t;
  const raw = await fetchPriceTrendsBundle(params);
  return {
    symbol: raw.ticker,
    as_of: raw.as_of,
    bars: raw.klines.map((bar) => ({
      symbol: raw.ticker,
      kline_t: raw.interval || '1D',
      bar_time: bar.datetime,
      open: bar.open,
      high: bar.high,
      low: bar.low,
      close: bar.close,
      vol: bar.volume ?? 0,
      amount: (bar.volume ?? 0) * bar.close,
    })),
  };
}

function mapIncomeDistributionItem(raw: Record<string, unknown>): EntityIncomeDistributionItem {
  const itemName = raw.item_name ?? raw.name;
  return {
    item_name: String(itemName ?? '').trim(),
    main_business_income: Number(raw.main_business_income ?? 0),
    mbi_ratio: Number(raw.mbi_ratio ?? raw.ratio ?? 0),
  };
}

function mapIncomeDistributionSlice(raw: {
  dimension: string;
  report_date: string | null;
  items: Record<string, unknown>[];
}): EntityIncomeDistributionSlice {
  const mainopType = INCOME_DIMENSION_TO_MAINOP[raw.dimension] ?? '1';
  return {
    mainop_type: mainopType,
    report_date: raw.report_date,
    items: raw.items.map(mapIncomeDistributionItem),
  };
}

export async function fetchCoreTickerIncome(params: {
  ticker: string;
  market?: MarketCode;
}): Promise<EntityTickerIncomeResponse> {
  const raw = await fetchCanonicalFinancialsBundle(params);
  const reportDate =
    raw.income_distributions.find((slice) => slice.report_date)?.report_date ?? raw.as_of;
  return {
    ticker: raw.ticker,
    market: raw.market,
    report_date: reportDate,
    distributions: raw.income_distributions.map(mapIncomeDistributionSlice),
  };
}

export { mapSectorOption };
