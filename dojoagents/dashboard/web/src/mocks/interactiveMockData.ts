import type {
  CoreTickerKlineResponse,
  CoreTickerPeBandResponse,
  CoreTickerQuoteResponse,
  CoreTickerSectorResponse,
} from '../api/dojoCore';
import type { BenchmarkCatalogResponse } from '../api/dojoMesh';
import type {
  FolioPortfolioDetailResponse,
  FolioPortfolioSummaryResponse,
} from '../api/dojoFolio';
import type { BenchmarkCard, DojoMeshOverview, MarketCode, MarketStats, SectorItem } from '../types/dojoMesh';
import type {
  CoreSectorOption,
  CoreTickerEventsResponse,
  CoreTickerFinIndicatorsResponse,
  CoreTickerIncomeResponse,
  CoreTickerNewsResponse,
  CoreTickerSearchItem,
} from '../types/dojoCore';
import type {
  SectorConstituentsResponse,
  SectorLevelKey,
  SectorPerformanceResponse,
  SectorScopeMetricsResponse,
} from '../types/dojoSphere';
import type { SectorTaxonomyDocument } from '../types/sectorTaxonomy';
import { fetchJson } from '../api/http';

export const USE_INTERACTIVE_MOCKS = import.meta.env.VITE_USE_MOCKS === 'true';

const API_DELAY_MS = 120;
const MARKET_CURRENCY: Record<MarketCode, string> = {
  us: 'USD',
  sh: 'CNY',
  hk: 'HKD',
};

const MARKET_LABEL: Record<MarketCode, string> = {
  us: 'US',
  sh: 'CN',
  hk: 'HK',
};

function delay<T>(value: T, ms = API_DELAY_MS): Promise<T> {
  return new Promise((resolve) => {
    window.setTimeout(() => resolve(structuredClone(value) as T), ms);
  });
}

function marketCapBase(market: MarketCode): number {
  if (market === 'us') return 3_100_000_000_000;
  if (market === 'hk') return 640_000_000_000;
  return 1_180_000_000_000;
}

const sectorOptions: CoreSectorOption[] = [
  {
    role: 'primary',
    level1Id: 'technology',
    level2Id: 'technology.semiconductor',
    level3Id: 'technology.semiconductor.chip_design',
    label: {
      level1: { zh: '科技', en: 'Technology' },
      level2: { zh: '半导体与集成电路', en: 'Semiconductors & Integrated Circuits' },
      level3: { zh: '芯片设计', en: 'Chip Design' },
    },
  },
  {
    role: 'secondary',
    level1Id: 'technology',
    level2Id: 'technology.software_services',
    level3Id: 'technology.software_services.ai_application',
    label: {
      level1: { zh: '科技', en: 'Technology' },
      level2: { zh: '软件与服务', en: 'Software & Services' },
      level3: { zh: '人工智能应用', en: 'AI Applications' },
    },
  },
];

const mockTickers: CoreTickerSearchItem[] = [
  { ticker: 'NVDA', market: 'us', name: { zh: '英伟达', en: 'NVIDIA' }, market_cap: 3_280_000_000_000 },
  { ticker: 'AAPL', market: 'us', name: { zh: '苹果', en: 'Apple' }, market_cap: 3_050_000_000_000 },
  { ticker: 'AMD', market: 'us', name: { zh: '超威半导体', en: 'AMD' }, market_cap: 270_000_000_000 },
  { ticker: 'TSM', market: 'us', name: { zh: '台积电', en: 'TSMC' }, market_cap: 840_000_000_000 },
  { ticker: '002371.SZ', market: 'sh', name: { zh: '北方华创', en: 'NAURA' }, market_cap: 170_000_000_000 },
  { ticker: '688981.SH', market: 'sh', name: { zh: '中芯国际', en: 'SMIC A' }, market_cap: 390_000_000_000 },
  { ticker: '000333.SZ', market: 'sh', name: { zh: '美的集团', en: 'Midea Group' }, market_cap: 470_000_000_000 },
  { ticker: '1810.HK', market: 'hk', name: { zh: '小米集团', en: 'Xiaomi' }, market_cap: 520_000_000_000 },
  { ticker: '0981.HK', market: 'hk', name: { zh: '中芯国际', en: 'SMIC' }, market_cap: 215_000_000_000 },
  { ticker: '1347.HK', market: 'hk', name: { zh: '华虹半导体', en: 'Hua Hong' }, market_cap: 48_000_000_000 },
];

function tickerIndex(ticker: string): number {
  const index = mockTickers.findIndex((item) => item.ticker === ticker);
  return index >= 0 ? index : 0;
}

function getTicker(ticker: string, market?: MarketCode): CoreTickerSearchItem {
  return (
    mockTickers.find((item) => item.ticker === ticker && (!market || item.market === market)) ??
    mockTickers.find((item) => item.ticker === ticker) ??
    mockTickers[0]!
  );
}

function buildBenchmark(symbol: string, market: MarketCode, seed: number): BenchmarkCard {
  const bars = Array.from({ length: 24 }, (_, i) => {
    const close = 100 + seed * 4 + Math.sin(i / 2 + seed) * 5 + i * (0.35 + seed * 0.02);
    return {
      datetime: `2026-05-${String(i + 10).padStart(2, '0')}`,
      close: Number(close.toFixed(2)),
    };
  });
  const last = bars[bars.length - 1]!.close;
  const prev = bars[bars.length - 2]!.close;
  return {
    market,
    symbol,
    name: { zh: `${MARKET_LABEL[market]} 指数 ${seed}`, en: `${MARKET_LABEL[market]} Index ${seed}` },
    price: last,
    change_percent: Number((((last - prev) / prev) * 100).toFixed(2)),
    kline: bars,
  };
}

function buildSector(name: string, code: string, market: MarketCode, change: number, strength: number): SectorItem {
  const samples = mockTickers.filter((item) => item.market === market).slice(0, 3);
  return {
    concept_code: code,
    name: { zh: name, en: code.replaceAll('-', ' ') },
    change_percent: change,
    avg_market_cap: marketCapBase(market) / 8,
    strength,
    sample_tickers: samples.map((item) => item.ticker),
    member_count: 36 + Math.round(strength / 4),
    members: samples.map((item, index) => ({
      ticker: item.ticker,
      name: item.name,
      last_price: 80 + index * 31 + strength / 3,
      market_cap: item.market_cap,
      change_percent: Number((change - index * 0.28).toFixed(2)),
    })),
  };
}

export function fetchMockDojoMeshOverview(): Promise<DojoMeshOverview> {
  const stats: Record<MarketCode, MarketStats> = {
    us: { market: 'us', listed_count: 5128, total_market_cap: 58_400_000_000_000, weighted_pe: 27.8, simple_pe: 31.2, pe_sample_count: 4312 },
    sh: { market: 'sh', listed_count: 5362, total_market_cap: 88_100_000_000_000, weighted_pe: 18.4, simple_pe: 29.1, pe_sample_count: 4720 },
    hk: { market: 'hk', listed_count: 2611, total_market_cap: 39_300_000_000_000, weighted_pe: 13.7, simple_pe: 20.5, pe_sample_count: 2196 },
  };
  const markets = Object.fromEntries(
    (['us', 'sh', 'hk'] as MarketCode[]).map((market, index) => [
      market,
      {
        stats: stats[market],
        benchmarks: [buildBenchmark(`MOCK-${market}-1`, market, index + 1), buildBenchmark(`MOCK-${market}-2`, market, index + 4)],
        default_benchmark: `MOCK-${market}-1`,
        gainers: [
          buildSector('芯片设计', 'chip-design', market, 2.6 - index * 0.3, 92),
          buildSector('云计算', 'cloud-computing', market, 1.8 - index * 0.2, 76),
          buildSector('AI 应用', 'ai-application', market, 1.2 - index * 0.15, 64),
        ],
        losers: [
          buildSector('消费电子', 'consumer-electronics', market, -0.9 - index * 0.15, 58),
          buildSector('地产链', 'property-chain', market, -1.4 - index * 0.2, 72),
        ],
      },
    ]),
  ) as DojoMeshOverview['markets'];

  return delay({ as_of: '2026-06-16', markets });
}

export function fetchMockBenchmarkCatalog(): Promise<BenchmarkCatalogResponse> {
  return fetchMockDojoMeshOverview().then((overview) => ({
    as_of: overview.as_of,
    markets: {
      us: { default_benchmark: 'MOCK-us-1', benchmarks: overview.markets.us.benchmarks },
      sh: { default_benchmark: 'MOCK-sh-1', benchmarks: overview.markets.sh.benchmarks },
      hk: { default_benchmark: 'MOCK-hk-1', benchmarks: overview.markets.hk.benchmarks },
    },
  }));
}

export function fetchMockCoreTickerSearch(params: { q: string; market?: MarketCode; limit?: number }): Promise<CoreTickerSearchItem[]> {
  const q = params.q.trim().toLowerCase();
  const items = mockTickers
    .filter((item) => !params.market || item.market === params.market)
    .filter((item) =>
      [item.ticker, item.name.zh, item.name.en].some((part) => part.toLowerCase().includes(q)),
    )
    .slice(0, params.limit ?? 30);
  return delay(items);
}

export function fetchMockCoreTickerSector(params: { ticker: string; market?: MarketCode }): Promise<CoreTickerSectorResponse> {
  const item = getTicker(params.ticker, params.market);
  return delay({ ticker: item.ticker, market: item.market, sector_options: sectorOptions });
}

export function fetchMockSectorConstituents(params: {
  level1Id: string;
  level2Id: string;
  level3Id: string;
  market: MarketCode;
  scope: SectorLevelKey;
}): Promise<SectorConstituentsResponse> {
  const items = mockTickers
    .filter((item) => item.market === params.market)
    .map((item, index) => ({
      ticker: item.ticker,
      market: item.market,
      name: item.name,
      currency: MARKET_CURRENCY[item.market],
      last_price: Number((86 + index * 23 + tickerIndex(item.ticker) * 4.7).toFixed(2)),
      change_percent: Number((2.1 - index * 0.55).toFixed(2)),
      window_change_percent: Number((5.8 - index * 0.7).toFixed(2)),
      turn_rate: Number((1.2 + index * 0.18).toFixed(2)),
      market_cap: item.market_cap,
      pe: Number((22 + index * 3.2).toFixed(2)),
      pb: Number((2.1 + index * 0.32).toFixed(2)),
      amount: 1_200_000_000 + index * 180_000_000,
    }));
  return delay({
    level1_id: params.level1Id,
    level2_id: params.level2Id,
    level3_id: params.level3Id,
    scope: params.scope,
    market: params.market,
    items,
  });
}

export function fetchMockSectorScopeMetrics(params: {
  level1Id: string;
  level2Id: string;
  level3Id: string;
}): Promise<SectorScopeMetricsResponse> {
  return delay({
    level1_id: params.level1Id,
    level2_id: params.level2Id,
    level3_id: params.level3Id,
    scopes: {
      L1: buildScopeStats(180),
      L2: buildScopeStats(88),
      L3: buildScopeStats(34),
    },
  });
}

function buildScopeStats(memberCount: number): SectorScopeMetricsResponse['scopes']['L1'] {
  return {
    us: { market: 'us', member_count: memberCount, total_market_cap: 6_800_000_000_000, weighted_pe: 31.5, pe_sample_count: memberCount - 9 },
    sh: { market: 'sh', member_count: memberCount - 18, total_market_cap: 1_900_000_000_000, weighted_pe: 42.4, pe_sample_count: memberCount - 24 },
    hk: { market: 'hk', member_count: memberCount - 42, total_market_cap: 860_000_000_000, weighted_pe: 21.2, pe_sample_count: memberCount - 51 },
  };
}

export function fetchMockSectorScopePerformance(params: {
  level1Id: string;
  level2Id: string;
  level3Id: string;
  scope: SectorLevelKey;
}): Promise<SectorPerformanceResponse> {
  const points = Array.from({ length: 36 }, (_, index) => ({
    date: `2026-05-${String(index + 1).padStart(2, '0')}`,
    us: Number((100 + Math.sin(index / 4) * 4 + index * 0.35).toFixed(2)),
    sh: Number((100 + Math.cos(index / 5) * 3 + index * 0.18).toFixed(2)),
    hk: Number((100 + Math.sin(index / 6) * 2.5 + index * 0.12).toFixed(2)),
  }));
  return delay({
    level1_id: params.level1Id,
    level2_id: params.level2Id,
    level3_id: params.level3Id,
    scope: params.scope,
    window_start: points[0]?.date ?? null,
    window_end: points[points.length - 1]?.date ?? null,
    points,
    series_by_market: {
      us: points.map((point) => ({ date: point.date, value: point.us ?? 100 })),
      sh: points.map((point) => ({ date: point.date, value: point.sh ?? 100 })),
      hk: points.map((point) => ({ date: point.date, value: point.hk ?? 100 })),
    },
    stats_by_market: {
      us: { cumulative_return_pct: 12.4, sharpe_ratio: 1.8, max_drawdown_pct: -4.2, calmar_ratio: 2.9, volatility_pct: 18.6, trading_days: 36 },
      sh: { cumulative_return_pct: 7.3, sharpe_ratio: 1.1, max_drawdown_pct: -6.8, calmar_ratio: 1.2, volatility_pct: 22.1, trading_days: 36 },
      hk: { cumulative_return_pct: 4.6, sharpe_ratio: 0.8, max_drawdown_pct: -5.5, calmar_ratio: 0.9, volatility_pct: 20.7, trading_days: 36 },
    },
    members_by_market: { us: 42, sh: 35, hk: 24 },
  });
}

export function fetchMockSectorTaxonomy(): Promise<SectorTaxonomyDocument> {
  return fetchJson<SectorTaxonomyDocument>('/taxonomy/stock_sector/v1.json');
}

export function fetchMockCoreTickerQuote(params: { ticker: string; market?: MarketCode }): Promise<CoreTickerQuoteResponse> {
  const item = getTicker(params.ticker, params.market);
  const index = tickerIndex(item.ticker);
  const preClose = 100 + index * 18.5;
  const changePercent = 2.4 - index * 0.32;
  const last = preClose * (1 + changePercent / 100);
  return delay({
    ticker: item.ticker,
    market: item.market,
    currency: MARKET_CURRENCY[item.market],
    last_price: Number(last.toFixed(2)),
    change: Number((last - preClose).toFixed(2)),
    change_percent: Number(changePercent.toFixed(2)),
    pre_close: Number(preClose.toFixed(2)),
    open: Number((preClose * 0.996).toFixed(2)),
    high: Number((last * 1.015).toFixed(2)),
    low: Number((preClose * 0.985).toFixed(2)),
    volume: 42_000_000 + index * 3_100_000,
    amount: 8_600_000_000 + index * 420_000_000,
    total_shares: 2_500_000_000 + index * 180_000_000,
    market_cap: item.market_cap,
    pe: Number((28 + index * 1.8).toFixed(2)),
    forward_pe: Number((24 + index * 1.4).toFixed(2)),
    pb: Number((4.8 - index * 0.18).toFixed(2)),
    turn_rate: Number((1.4 + index * 0.12).toFixed(2)),
    exchange_name: item.market.toUpperCase(),
    industry: 'Semiconductors',
    sector: 'Technology',
    country: item.market === 'us' ? 'US' : item.market === 'hk' ? 'HK' : 'CN',
  });
}

export function fetchMockCoreTickerKline(params: {
  ticker: string;
  market?: MarketCode;
  kline_t?: string;
  limit?: number;
}): Promise<CoreTickerKlineResponse> {
  const item = getTicker(params.ticker, params.market);
  const interval = params.kline_t ?? '1D';
  const count = Math.min(params.limit ?? 120, interval === '5m' ? 120 : 270);
  const seed = tickerIndex(item.ticker) + 1;
  let close = 80 + seed * 12;
  const bars = Array.from({ length: count }, (_, index) => {
    const drift = Math.sin(index / 8 + seed) * 1.2 + 0.18;
    const open = close;
    close = Math.max(8, close + drift);
    const date = interval === '5m'
      ? `2026-06-16 10:${String(index % 60).padStart(2, '0')}:00`
      : `2026-${String(Math.floor(index / 26) + 1).padStart(2, '0')}-${String((index % 26) + 1).padStart(2, '0')}`;
    return {
      symbol: item.ticker,
      kline_t: interval,
      bar_time: date,
      open: Number(open.toFixed(2)),
      high: Number((Math.max(open, close) * 1.012).toFixed(2)),
      low: Number((Math.min(open, close) * 0.988).toFixed(2)),
      close: Number(close.toFixed(2)),
      vol: 8_000_000 + index * 90_000,
      amount: 720_000_000 + index * 12_000_000,
    };
  });
  return delay({ symbol: item.ticker, as_of: '2026-06-16', bars });
}

export function fetchMockCoreTickerPeBand(params: { ticker: string; market?: MarketCode; limit?: number }): Promise<CoreTickerPeBandResponse> {
  const item = getTicker(params.ticker, params.market);
  const seed = tickerIndex(item.ticker) + 1;
  const count = params.limit ?? 252;
  const points = Array.from({ length: count }, (_, index) => {
    const mean = 26 + seed * 1.2;
    const pe = mean + Math.sin(index / 18 + seed) * 5;
    return {
      date: `2026-${String(Math.floor(index / 26) + 1).padStart(2, '0')}-${String((index % 26) + 1).padStart(2, '0')}`,
      pe: Number(pe.toFixed(2)),
      mean: Number(mean.toFixed(2)),
      upper1: Number((mean * 1.18).toFixed(2)),
      lower1: Number((mean * 0.84).toFixed(2)),
      upper2: Number((mean * 1.36).toFixed(2)),
      lower2: Number((mean * 0.7).toFixed(2)),
    };
  });
  return delay({ ticker: item.ticker, market: item.market, as_of: '2026-06-16', total_shares: 2_800_000_000, points });
}

export function fetchMockCoreTickerFinIndicators(params: {
  ticker: string;
  market?: MarketCode;
  limit?: number;
}): Promise<CoreTickerFinIndicatorsResponse> {
  const item = getTicker(params.ticker, params.market);
  const seed = tickerIndex(item.ticker) + 1;
  const count = params.limit ?? 20;
  const quarterMeta: Record<number, { dateSuffix: string; reportName: string; season: string }> = {
    1: { dateSuffix: '03-31', reportName: '一季报', season: '一季度' },
    2: { dateSuffix: '06-30', reportName: '中报', season: '二季度' },
    3: { dateSuffix: '09-30', reportName: '三季报', season: '三季度' },
    4: { dateSuffix: '12-31', reportName: '年报', season: '四季度' },
  };
  const items = Array.from({ length: count }, (_, index) => {
    const year = 2026 - Math.floor(index / 4);
    const quarter = 4 - (index % 4);
    const meta = quarterMeta[quarter]!;
    const revenue = 42_000_000_000 + seed * 2_000_000_000 - index * 1_150_000_000;
    return {
      symbol: item.ticker,
      report_date: `${year}-${meta.dateSuffix}`,
      std_report_date: `${year}-${meta.dateSuffix}`,
      report_type: 'quarterly',
      report_period_name: `${year}年${meta.reportName}`,
      season_label: meta.season,
      total_operating_revenue: revenue,
      total_operating_rev_yoy: 9 + seed * 1.7 - index * 0.35,
      net_profit_attr_parent: revenue * 0.21,
      gross_margin: 38 + seed * 2.1,
      net_margin: 18 + seed * 0.7,
      roe_weighted: 16 + seed * 1.3,
      roa: 9 + seed * 0.5,
      eps_basic: 1.2 + seed * 0.18,
      eps_ttm: 5.2 + seed * 0.4,
      pe_ttm: 28 + seed * 1.7,
      pb_ttm: 4 + seed * 0.22,
      bps: 18 + seed,
      dividend_rate: 0.8 + seed * 0.08,
      divi_ratio: 18 + seed,
      total_market_cap: item.market_cap,
      hksk_market_cap: item.market === 'hk' ? item.market_cap * 0.42 : null,
    };
  });
  return delay({ ticker: item.ticker, market: item.market, report_type: 'quarterly', as_of: '2026-06-16', source: 'local', items });
}

export function fetchMockCoreTickerEvents(params: { ticker: string; market?: MarketCode }): Promise<CoreTickerEventsResponse> {
  const item = getTicker(params.ticker, params.market);
  return delay({
    ticker: item.ticker,
    market: item.market,
    as_of: '2026-06-16',
    source: 'local',
    items: [
      { id: `${item.ticker}-earnings`, symbol: item.ticker, event_date: '2026-07-18', type_name: '财报', title: `${item.name.zh} 预计发布季度业绩`, content: 'Mock calendar event for interactive preview.' },
      { id: `${item.ticker}-dividend`, symbol: item.ticker, event_date: '2026-08-03', type_name: '分红', title: `${item.name.zh} 分红除权观察`, content: 'Mock dividend checkpoint.' },
    ],
  });
}

export function fetchMockCoreTickerNews(params: { ticker: string; market?: MarketCode }): Promise<CoreTickerNewsResponse> {
  const item = getTicker(params.ticker, params.market);
  return delay({
    ticker: item.ticker,
    market: item.market,
    as_of: '2026-06-16',
    source: 'local',
    items: [
      { id: `${item.ticker}-n1`, publish_date: '2026-06-16', title: `${item.name.zh} 供应链景气度继续改善`, url: '#', source: 'AlphaDojo Mock' },
      { id: `${item.ticker}-n2`, publish_date: '2026-06-15', title: `${item.name.en} expands AI infrastructure roadmap`, url: '#', source: 'AlphaDojo Mock' },
    ],
  });
}

export function fetchMockCoreTickerIncome(params: { ticker: string; market?: MarketCode }): Promise<CoreTickerIncomeResponse> {
  const item = getTicker(params.ticker, params.market);
  return delay({
    ticker: item.ticker,
    market: item.market,
    report_date: '2026-03-31',
    distributions: [
      {
        mainop_type: '1',
        report_date: '2026-03-31',
        items: [
          { item_name: 'Data center', main_business_income: 36_000_000_000, mbi_ratio: 54 },
          { item_name: 'Devices', main_business_income: 19_000_000_000, mbi_ratio: 28 },
          { item_name: 'Services', main_business_income: 12_000_000_000, mbi_ratio: 18 },
        ],
      },
    ],
  });
}

let portfolioSeq = 3;
let mockPortfolios: FolioPortfolioDetailResponse[] = [
  {
    id: 'mock-growth',
    name: '全球科技增长',
    subtitle: 'AI + 半导体核心仓',
    kind: 'manual',
    today_change: 1.28,
    net_value_usd: 1_286_400,
    config: { start_date: '2025-06-16', cost_date: '2025-06-16', capital_by_market: { us: 800_000, sh: 250_000, hk: 180_000 } },
    holdings: [
      buildHolding('NVDA', 120),
      buildHolding('AAPL', 80),
      buildHolding('002371.SZ', 600),
      buildHolding('1810.HK', 2000),
    ],
    kpis: [
      { key: 'netValue', value: '$1.29M', delta: '+1.28%', delta_tone: 'positive', hint: 'Mock portfolio net value' },
      { key: 'cumulativeReturn', value: '+18.6%', delta: '+2.1% MTD', delta_tone: 'positive' },
      { key: 'sharpe', value: '1.42', delta_tone: 'neutral' },
      { key: 'maxDrawdown', value: '-7.8%', delta_tone: 'risk' },
    ],
    performance: buildPortfolioPerformance(1.18),
    net_value_by_market: { us: 856_000, sh: 248_000, hk: 182_400 },
  },
  {
    id: 'mock-balanced',
    name: '跨市场均衡',
    subtitle: '美股 / A股 / 港股分散',
    kind: 'agent',
    today_change: -0.18,
    net_value_usd: 932_700,
    config: { start_date: '2025-06-16', cost_date: '2025-06-16', capital_by_market: { us: 350_000, sh: 350_000, hk: 250_000 } },
    holdings: [buildHolding('TSM', 90), buildHolding('000333.SZ', 1800), buildHolding('0981.HK', 3200)],
    kpis: [
      { key: 'netValue', value: '$932.7K', delta: '-0.18%', delta_tone: 'negative' },
      { key: 'cumulativeReturn', value: '+6.4%', delta_tone: 'positive' },
      { key: 'sharpe', value: '0.96', delta_tone: 'neutral' },
      { key: 'maxDrawdown', value: '-5.2%', delta_tone: 'risk' },
    ],
    performance: buildPortfolioPerformance(1.06),
    net_value_by_market: { us: 368_000, sh: 329_000, hk: 235_700 },
  },
];

function buildHolding(ticker: string, shares: number): NonNullable<FolioPortfolioDetailResponse['holdings']>[number] {
  const item = getTicker(ticker);
  const index = tickerIndex(ticker);
  const price = 96 + index * 18.2;
  const cost = price * 0.88;
  return {
    ticker: item.ticker,
    name: item.name.zh,
    market: item.market,
    shares,
    weight: 0,
    cost: Number(cost.toFixed(2)),
    open_date: '2025-06-16',
    uses_default_open_date: true,
    manual_shares: false,
    price: Number(price.toFixed(2)),
    change_percent: Number((1.9 - index * 0.35).toFixed(2)),
    sector: 'Technology',
    market_value: Number((shares * price).toFixed(2)),
  };
}

function normalizePortfolio(portfolio: FolioPortfolioDetailResponse): FolioPortfolioDetailResponse {
  const holdings = portfolio.holdings ?? [];
  const total = holdings.reduce((sum, holding) => sum + holding.market_value, 0);
  return {
    ...portfolio,
    holdings: holdings.map((holding) => ({
      ...holding,
      weight: total > 0 ? Number(((holding.market_value / total) * 100).toFixed(1)) : 0,
    })),
  };
}

function buildPortfolioPerformance(multiplier: number): NonNullable<FolioPortfolioDetailResponse['performance']> {
  const dates = Array.from({ length: 12 }, (_, index) => `2025-${String(index + 7).padStart(2, '0')}-16`);
  return {
    dates,
    portfolio: dates.map((_, index) => Number((100 * multiplier + Math.sin(index / 2) * 3 + index * 1.2).toFixed(2))),
    benchmark: dates.map((_, index) => Number((100 + Math.cos(index / 3) * 2 + index * 0.8).toFixed(2))),
  };
}

export function fetchMockFolioPortfolios(): Promise<FolioPortfolioSummaryResponse[]> {
  return delay(mockPortfolios.map((portfolio) => ({
    id: portfolio.id,
    name: portfolio.name,
    subtitle: portfolio.subtitle,
    kind: portfolio.kind,
    today_change: portfolio.today_change,
    net_value_usd: portfolio.net_value_usd,
  })));
}

export function fetchMockFolioPortfolioDetail(portfolioId: string): Promise<FolioPortfolioDetailResponse> {
  return delay(normalizePortfolio(findPortfolio(portfolioId)));
}

export function createMockFolioPortfolio(name: string): Promise<FolioPortfolioDetailResponse> {
  const created: FolioPortfolioDetailResponse = {
    id: `mock-custom-${portfolioSeq}`,
    name,
    subtitle: '本地 mock 组合',
    kind: 'manual',
    today_change: 0,
    net_value_usd: 0,
    config: { start_date: '2025-06-16', cost_date: '2025-06-16', capital_by_market: { us: 1_000_000, sh: 1_000_000, hk: 1_000_000 } },
    holdings: [],
    kpis: null,
    performance: buildPortfolioPerformance(1),
    net_value_by_market: { us: 0, sh: 0, hk: 0 },
  };
  portfolioSeq += 1;
  mockPortfolios = [...mockPortfolios, created];
  return delay(created);
}

export function updateMockFolioPortfolio(
  portfolioId: string,
  payload: {
    name?: string;
    config?: { startDate: string; capitalByMarket: Record<MarketCode, number> };
    shares_by_ticker?: Record<string, number>;
    manual_shares_by_ticker?: Record<string, boolean>;
    open_date_by_ticker?: Record<string, string | null>;
  },
): Promise<FolioPortfolioDetailResponse> {
  const portfolio = findPortfolio(portfolioId);
  if (payload.name) portfolio.name = payload.name;
  if (payload.config) {
    portfolio.config = {
      start_date: payload.config.startDate,
      cost_date: payload.config.startDate,
      capital_by_market: payload.config.capitalByMarket,
    };
  }
  if (payload.shares_by_ticker && portfolio.holdings) {
    portfolio.holdings = portfolio.holdings
      .map((holding) => {
        const shares = payload.shares_by_ticker?.[holding.ticker] ?? holding.shares;
        return {
          ...holding,
          shares,
          manual_shares: payload.manual_shares_by_ticker?.[holding.ticker] ?? holding.manual_shares,
          market_value: Number((shares * holding.price).toFixed(2)),
        };
      })
      .filter((holding) => holding.shares > 0);
  }
  if (payload.open_date_by_ticker && portfolio.holdings) {
    portfolio.holdings = portfolio.holdings.map((holding) => (
      payload.open_date_by_ticker && holding.ticker in payload.open_date_by_ticker
        ? {
            ...holding,
            open_date: payload.open_date_by_ticker[holding.ticker] ?? portfolio.config?.start_date ?? null,
            uses_default_open_date: payload.open_date_by_ticker[holding.ticker] == null,
          }
        : holding
    ));
  }
  return delay(normalizePortfolio(portfolio));
}

export function deleteMockFolioPortfolio(portfolioId: string): Promise<void> {
  mockPortfolios = mockPortfolios.filter((portfolio) => portfolio.id !== portfolioId);
  return delay(undefined);
}

export function addMockFolioHolding(
  portfolioId: string,
  payload: { ticker: string; market?: MarketCode; shares?: number },
): Promise<FolioPortfolioDetailResponse> {
  const portfolio = findPortfolio(portfolioId);
  const item = getTicker(payload.ticker, payload.market);
  const exists = portfolio.holdings?.some((holding) => holding.ticker === item.ticker);
  if (!exists) {
    portfolio.holdings = [...(portfolio.holdings ?? []), buildHolding(item.ticker, payload.shares ?? defaultShares(item.market))];
  }
  return delay(normalizePortfolio(portfolio));
}

export function autoAllocateMockFolioPortfolio(
  portfolioId: string,
  market?: MarketCode,
): Promise<FolioPortfolioDetailResponse> {
  const portfolio = findPortfolio(portfolioId);
  portfolio.holdings = (portfolio.holdings ?? []).map((holding) => {
    if (market && holding.market !== market) return holding;
    const shares = defaultShares(holding.market);
    return { ...holding, shares, manual_shares: false, market_value: Number((shares * holding.price).toFixed(2)) };
  });
  return delay(normalizePortfolio(portfolio));
}

function findPortfolio(portfolioId: string): FolioPortfolioDetailResponse {
  const portfolio = mockPortfolios.find((item) => item.id === portfolioId);
  if (!portfolio) throw new Error(`Mock portfolio not found: ${portfolioId}`);
  return portfolio;
}

function defaultShares(market: MarketCode): number {
  if (market === 'us') return 100;
  if (market === 'hk') return 2000;
  return 1000;
}
