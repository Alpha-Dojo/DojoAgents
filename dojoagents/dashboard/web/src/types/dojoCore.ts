import type { BilingualText, MarketCode } from './dojoMesh';

export interface CoreSectorLabelPath {
  level1: BilingualText;
  level2: BilingualText;
  level3: BilingualText;
}

export interface CoreSectorOption {
  role: 'primary' | 'secondary';
  level1Id: string;
  level2Id: string;
  level3Id: string;
  label: CoreSectorLabelPath;
}

export interface CoreSectorCrumb {
  level: 'L1' | 'L2' | 'L3';
  name: BilingualText;
  level1Id: string;
  level2Id: string;
  level3Id: string;
}

export interface CoreTickerSearchItem {
  ticker: string;
  market: MarketCode;
  name: BilingualText;
  market_cap: number;
}

/** Raw financial indicator row from /dojo-core/ticker/fin-indicators */
export interface StockFinIndicatorRow {
  symbol: string;
  report_date?: string | null;
  std_report_date?: string | null;
  report_type?: string | null;
  report_period_name?: string | null;
  season_label?: string | null;
  total_operating_revenue?: number | null;
  total_operating_rev_yoy?: number | null;
  net_profit_attr_parent?: number | null;
  gross_margin?: number | null;
  net_margin?: number | null;
  roe_weighted?: number | null;
  roa?: number | null;
  eps_basic?: number | null;
  eps_ttm?: number | null;
  pe_ttm?: number | null;
  pb_ttm?: number | null;
  bps?: number | null;
  dividend_rate?: number | null;
  divi_ratio?: number | null;
  total_market_cap?: number | null;
  hksk_market_cap?: number | null;
}

export interface CoreTickerFinIndicatorsResponse {
  ticker: string;
  market: MarketCode;
  report_type: string;
  as_of: string | null;
  source: 'local' | 'remote';
  items: StockFinIndicatorRow[];
}

export interface CoreQuoteSnapshot {
  price: number;
  change: number;
  changePercent: number;
  currency: string;
  afterHoursPrice?: number;
  afterHoursChange?: number;
  afterHoursChangePercent?: number;
}

export interface CoreKeyMetric {
  labelKey: string;
  value: string;
  subValue?: string;
  /** Full text for tooltip when value is truncated. */
  title?: string;
}

export interface CoreKlineBar {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  amount: number;
}

/** Calendar event marker on the K-line chart (earnings, dividends, …). */
export type CoreChartEventKind = 'earnings';

export interface CoreChartEvent {
  id: string;
  kind: CoreChartEventKind;
  /** Report / event calendar date (YYYY-MM-DD). */
  date: string;
  /** Tooltip label, e.g. 2024年三季报. */
  label: string;
  /** Fiscal quarter code for hover copy, e.g. Q2. */
  quarterCode: string;
}

export type CoreKlineInterval = '5m' | '1D' | '1W' | '1M';

export interface CorePeBandPoint {
  date: string;
  pe: number;
  mean: number;
  upper1: number;
  lower1: number;
  upper2: number;
  lower2: number;
}

export interface CoreFinancialYear {
  year: string;
  revenue: number;
  netProfit: number;
  /** Same-quarter YoY revenue growth; null when prior-year quarter is unavailable. */
  revenueYoY: number | null;
}

export interface CoreProfitabilityAxis {
  key: string;
  value: number;
  max: number;
  percentile: number;
  beatsLabelKey: string;
}

export interface CoreEpsForecast {
  year: string;
  eps: number;
}

export interface CoreAnalystRating {
  buy: number;
  hold: number;
  sell: number;
}

export interface CoreAnalystSnapshot {
  epsForecast: CoreEpsForecast[];
  rating: CoreAnalystRating;
  targetPriceAvg: number;
  targetPriceCurrent: number;
  currency: string;
}

export interface CoreInsiderTrade {
  date: string;
  executive: string;
  actionKey: string;
  shares: number;
}

export interface CoreRiskSnapshot {
  earningsDate: string;
  earningsDaysRemaining: number;
  insiderTrades: CoreInsiderTrade[];
  noMajorWarnings: boolean;
}

/** Raw event row from /dojo-core/ticker/events */
export interface StockEventRow {
  id?: string | null;
  symbol?: string | null;
  event_date?: string | null;
  remind_date?: string | null;
  notice_date?: string | null;
  event_type?: string | null;
  specific_eventtype?: string | null;
  type_name?: string | null;
  event_type_name?: string | null;
  level1_content?: string | null;
  level2_content?: string | null;
  title?: string | null;
  content?: string | null;
  event_content?: string | null;
}

export interface CoreTickerEventsResponse {
  ticker: string;
  market: MarketCode;
  as_of: string | null;
  source: 'local' | 'remote';
  items: StockEventRow[];
}

export interface CoreStockEventItem {
  id: string;
  date: string;
  typeLabel: string;
  content: string;
}

/** Raw news row from /dojo-core/ticker/news */
export interface StockNewsRow {
  id?: string | null;
  publish_date?: string | null;
  title?: string | null;
  url?: string | null;
  description?: string | null;
  source?: string | null;
}

export interface CoreTickerNewsResponse {
  ticker: string;
  market: MarketCode;
  as_of: string | null;
  source: 'local' | 'remote';
  items: StockNewsRow[];
}

export interface CoreStockNewsItem {
  id: string;
  date: string;
  title: string;
  url: string;
}

export type CoreIncomeMainopType = '1' | '2' | '3';

export interface CoreIncomeDistributionItem {
  item_name: string;
  main_business_income: number;
  mbi_ratio: number;
}

export interface CoreIncomeDistributionSlice {
  mainop_type: CoreIncomeMainopType;
  report_date: string | null;
  items: CoreIncomeDistributionItem[];
}

export interface CoreTickerIncomeResponse {
  ticker: string;
  market: MarketCode;
  report_date: string | null;
  distributions: CoreIncomeDistributionSlice[];
}

export interface CoreAssetSnapshot {
  ticker: string;
  market: MarketCode;
  name: BilingualText;
  sectorPath: CoreSectorCrumb[];
  quote: CoreQuoteSnapshot;
  metricRows: CoreKeyMetric[][];
  kline: CoreKlineBar[];
  peBand: CorePeBandPoint[];
  financials: CoreFinancialYear[];
  profitability: CoreProfitabilityAxis[];
  analyst: CoreAnalystSnapshot;
  risk: CoreRiskSnapshot;
}
