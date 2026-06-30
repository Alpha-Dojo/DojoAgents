import type { BilingualText, MarketCode } from './market';

export interface EntitySectorLabelPath {
  level1: BilingualText;
  level2: BilingualText;
  level3: BilingualText;
}

export interface EntitySectorOption {
  role: 'primary' | 'secondary';
  level1Id: string;
  level2Id: string;
  level3Id: string;
  label: EntitySectorLabelPath;
}

export interface EntitySectorCrumb {
  level: 'L1' | 'L2' | 'L3';
  name: BilingualText;
  level1Id: string;
  level2Id: string;
  level3Id: string;
}

export interface EntityTickerSearchItem {
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
  /** Natural calendar period from backend (+2 on fiscal report_period_name). */
  calendar_year?: number | null;
  calendar_quarter?: number | null;
  calendar_period_label?: string | null;
  calendar_period_index?: number | null;
}

export interface EntityTickerFinIndicatorsResponse {
  ticker: string;
  market: MarketCode;
  report_type: string;
  as_of: string | null;
  source: 'local' | 'remote';
  items: StockFinIndicatorRow[];
}

export interface EntityQuoteSnapshot {
  price: number;
  change: number;
  changePercent: number;
  currency: string;
  afterHoursPrice?: number;
  afterHoursChange?: number;
  afterHoursChangePercent?: number;
}

export interface EntityKeyMetric {
  labelKey: string;
  value: string;
  subValue?: string;
  /** Full text for tooltip when value is truncated. */
  title?: string;
}

export interface EntityKlineBar {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  amount: number;
}

/** Calendar event marker on the K-line chart (earnings, dividends, …). */
export type EntityChartEventKind = 'earnings';

export interface EntityChartEvent {
  id: string;
  kind: EntityChartEventKind;
  /** Report / event calendar date (YYYY-MM-DD). */
  date: string;
  /** Tooltip label, e.g. 2024年三季报. */
  label: string;
  /** Fiscal quarter code for hover copy, e.g. Q2. */
  quarterCode: string;
}

export type EntityKlineInterval = '5m' | '1D' | '1W' | '1M';

export interface EntityPeBandPoint {
  date: string;
  pe: number;
  mean: number;
  upper1: number;
  lower1: number;
  upper2: number;
  lower2: number;
}

export interface EntityFinancialYear {
  year: string;
  reportDate?: string;
  revenue: number;
  netProfit: number;
  /** Same-quarter YoY revenue growth; null when prior-year quarter is unavailable. */
  revenueYoY: number | null;
}

export interface EntityProfitabilityAxis {
  key: string;
  value: number;
  max: number;
  percentile: number;
  beatsLabelKey: string;
}

export interface EntityEpsForecast {
  year: string;
  eps: number;
}

export interface EntityAnalystRating {
  buy: number;
  hold: number;
  sell: number;
}

export interface EntityAnalystSnapshot {
  epsForecast: EntityEpsForecast[];
  rating: EntityAnalystRating;
  targetPriceAvg: number;
  targetPriceCurrent: number;
  currency: string;
}

export interface EntityInsiderTrade {
  date: string;
  executive: string;
  actionKey: string;
  shares: number;
}

export interface EntityRiskSnapshot {
  earningsDate: string;
  earningsDaysRemaining: number;
  insiderTrades: EntityInsiderTrade[];
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

export interface EntityTickerEventsResponse {
  ticker: string;
  market: MarketCode;
  as_of: string | null;
  source: 'local' | 'remote';
  items: StockEventRow[];
}

export interface EntityStockEventItem {
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

export interface EntityTickerNewsResponse {
  ticker: string;
  market: MarketCode;
  as_of: string | null;
  source: 'local' | 'remote';
  items: StockNewsRow[];
}

export interface EntityStockNewsItem {
  id: string;
  date: string;
  title: string;
  url: string;
}

export type EntityIncomeMainopType = '1' | '2' | '3';

export interface EntityIncomeDistributionItem {
  item_name: string;
  main_business_income: number;
  mbi_ratio: number;
}

export interface EntityIncomeDistributionSlice {
  mainop_type: EntityIncomeMainopType;
  report_date: string | null;
  items: EntityIncomeDistributionItem[];
}

export interface EntityTickerIncomeResponse {
  ticker: string;
  market: MarketCode;
  report_date: string | null;
  distributions: EntityIncomeDistributionSlice[];
}

export interface EntityAssetSnapshot {
  ticker: string;
  market: MarketCode;
  name: BilingualText;
  sectorPath: EntitySectorCrumb[];
  quote: EntityQuoteSnapshot;
  metricRows: EntityKeyMetric[][];
  kline: EntityKlineBar[];
  peBand: EntityPeBandPoint[];
  financials: EntityFinancialYear[];
  profitability: EntityProfitabilityAxis[];
  analyst: EntityAnalystSnapshot;
  risk: EntityRiskSnapshot;
}
