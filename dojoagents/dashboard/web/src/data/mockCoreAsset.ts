import type { CoreTickerContext } from '../navigation/coreContext';
import type {
  CoreAssetSnapshot,
  CoreKlineBar,
  CorePeBandPoint,
} from '../types/dojoCore';

function hashSeed(text: string): number {
  let h = 2166136261;
  for (let i = 0; i < text.length; i += 1) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function mulberry32(seed: number) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function buildKline(seedKey: string, basePrice: number, bars: number): CoreKlineBar[] {
  const rand = mulberry32(hashSeed(seedKey));
  const out: CoreKlineBar[] = [];
  let price = basePrice * 0.88;
  const start = new Date('2024-02-01');

  for (let i = 0; i < bars; i += 1) {
    const d = new Date(start);
    d.setDate(d.getDate() + i);
    const drift = (rand() - 0.48) * basePrice * 0.018;
    const open = price;
    const close = Math.max(1, open + drift);
    const high = Math.max(open, close) + rand() * basePrice * 0.012;
    const low = Math.min(open, close) - rand() * basePrice * 0.012;
    const volume = Math.round(8_000_000 + rand() * 22_000_000);
    const amount = volume * ((open + close) / 2);
    out.push({
      date: d.toISOString().slice(0, 10),
      open: +open.toFixed(2),
      high: +high.toFixed(2),
      low: +low.toFixed(2),
      close: +close.toFixed(2),
      volume,
      amount,
    });
    price = close;
  }
  return out;
}

function buildPeBand(seedKey: string): CorePeBandPoint[] {
  const rand = mulberry32(hashSeed(`${seedKey}-pe`));
  const out: CorePeBandPoint[] = [];
  const mean = 22;
  for (let year = 2018; year <= 2024; year += 1) {
    for (let month = 1; month <= 12; month += 3) {
      const pe = mean + (rand() - 0.5) * 14;
      out.push({
        date: `${year}-${String(month).padStart(2, '0')}`,
        pe: +pe.toFixed(1),
        mean,
        upper1: mean + 4,
        lower1: mean - 4,
        upper2: mean + 8,
        lower2: mean - 8,
      });
    }
  }
  return out;
}

const TSM_SNAPSHOT: CoreAssetSnapshot = {
  ticker: 'TSM',
  market: 'us',
  name: {
    zh: '台湾积体电路制造股份有限公司',
    en: 'Taiwan Semiconductor Manufacturing Co., Ltd.',
  },
  sectorPath: [
    { level: 'L1', name: { zh: '科技', en: 'Technology' }, level1Id: '', level2Id: '', level3Id: '' },
    {
      level: 'L2',
      name: { zh: '半导体与集成电路', en: 'Semiconductors & Integrated Circuits' },
      level1Id: '',
      level2Id: '',
      level3Id: '',
    },
    {
      level: 'L3',
      name: { zh: '集成电路制造', en: 'Wafer Fabrication' },
      level1Id: '',
      level2Id: '',
      level3Id: '',
    },
  ],
  quote: {
    price: 168.45,
    change: 3.2,
    changePercent: 1.94,
    currency: 'USD',
    afterHoursPrice: 169.1,
    afterHoursChange: 0.65,
    afterHoursChangePercent: 0.39,
  },
  metricRows: [
    [
      { labelKey: 'marketCap', value: '873.4B', subValue: 'USD' },
      { labelKey: 'totalShares', value: '15.3B' },
      { labelKey: 'peTtm', value: '28.5' },
      { labelKey: 'peDynamic', value: '24.1' },
      { labelKey: 'pbRatio', value: '7.6' },
      { labelKey: 'epsBasic', value: '6.42', subValue: 'USD' },
      { labelKey: 'roe', value: '29.7%' },
    ],
    [
      { labelKey: 'roa', value: '18.5%' },
      { labelKey: 'grossMargin', value: '53.4%' },
      { labelKey: 'netMargin', value: '38.2%' },
      { labelKey: 'dividendYield', value: '1.15%' },
      { labelKey: 'turnover', value: '0.42%' },
      { labelKey: 'week52Range', value: '178.60 / 96.11' },
    ],
  ],
  kline: buildKline('TSM', 168.45, 72),
  peBand: buildPeBand('TSM'),
  financials: [
    { year: '2019', revenue: 346.0, netProfit: 117.0, revenueYoY: 3.7 },
    { year: '2020', revenue: 455.0, netProfit: 181.0, revenueYoY: 31.5 },
    { year: '2021', revenue: 568.0, netProfit: 213.0, revenueYoY: 24.9 },
    { year: '2022', revenue: 760.0, netProfit: 333.0, revenueYoY: 33.8 },
    { year: '2023', revenue: 693.0, netProfit: 268.0, revenueYoY: -8.8 },
  ],
  profitability: [
    { key: 'grossMargin', value: 53.4, max: 60, percentile: 89, beatsLabelKey: 'beats89' },
    { key: 'netMargin', value: 38.2, max: 45, percentile: 95, beatsLabelKey: 'beats95' },
    { key: 'roe', value: 29.7, max: 35, percentile: 91, beatsLabelKey: 'beats91' },
    { key: 'roa', value: 18.5, max: 25, percentile: 85, beatsLabelKey: 'beats85' },
  ],
  analyst: {
    epsForecast: [
      { year: '2024E', eps: 6.78 },
      { year: '2025E', eps: 9.3 },
      { year: '2026E', eps: 11.33 },
    ],
    rating: { buy: 80, hold: 15, sell: 5 },
    targetPriceAvg: 185.2,
    targetPriceCurrent: 168.45,
    currency: 'USD',
  },
  risk: {
    earningsDate: '2024-07-18',
    earningsDaysRemaining: 45,
    insiderTrades: [
      {
        date: '2024-04',
        executive: 'C.C. Wei',
        actionKey: 'sold',
        shares: 1000,
      },
    ],
    noMajorWarnings: true,
  },
};

function normalizeTicker(ticker: string): string {
  return ticker.split('.')[0]?.toUpperCase() ?? ticker.toUpperCase();
}

function buildGenericSnapshot(ctx: CoreTickerContext): CoreAssetSnapshot {
  const ticker = normalizeTicker(ctx.ticker);
  const market = ctx.market ?? 'us';
  const basePrice = 50 + (hashSeed(ticker) % 300);
  const changePct = ((hashSeed(`${ticker}-chg`) % 400) - 200) / 100;
  const change = +(basePrice * (changePct / 100)).toFixed(2);

  return {
    ticker,
    market,
    name: {
      zh: ctx.name_zh || ticker,
      en: ctx.name_en || ticker,
    },
    sectorPath: [
      { level: 'L1', name: { zh: '科技', en: 'Technology' }, level1Id: '', level2Id: '', level3Id: '' },
      { level: 'L2', name: { zh: '行业分组', en: 'Industry Group' }, level1Id: '', level2Id: '', level3Id: '' },
      { level: 'L3', name: { zh: '细分赛道', en: 'Sub-sector' }, level1Id: '', level2Id: '', level3Id: '' },
    ],
    quote: {
      price: basePrice,
      change,
      changePercent: changePct,
      currency: market === 'us' ? 'USD' : market === 'hk' ? 'HKD' : 'CNY',
      afterHoursPrice: +(basePrice + change * 0.2).toFixed(2),
      afterHoursChange: +(change * 0.2).toFixed(2),
      afterHoursChangePercent: +(changePct * 0.2).toFixed(2),
    },
    metricRows: [
      [
        { labelKey: 'marketCap', value: `${(hashSeed(ticker) % 900 + 100) / 10}B` },
        { labelKey: 'totalShares', value: `${(hashSeed(ticker) % 50 + 10) / 10}B` },
        { labelKey: 'peTtm', value: `${(hashSeed(ticker) % 40 + 10).toFixed(1)}` },
        { labelKey: 'peDynamic', value: `${(hashSeed(ticker) % 35 + 8).toFixed(1)}` },
        { labelKey: 'pbRatio', value: `${((hashSeed(ticker) % 80) / 10 + 1).toFixed(1)}` },
        { labelKey: 'epsBasic', value: `${((hashSeed(ticker) % 500) / 100).toFixed(2)}` },
        { labelKey: 'roe', value: `${((hashSeed(ticker) % 300) / 10).toFixed(1)}%` },
      ],
      [
        { labelKey: 'roa', value: `${((hashSeed(ticker) % 200) / 10).toFixed(1)}%` },
        { labelKey: 'grossMargin', value: `${((hashSeed(ticker) % 500) / 10).toFixed(1)}%` },
        { labelKey: 'netMargin', value: `${((hashSeed(ticker) % 300) / 10).toFixed(1)}%` },
        { labelKey: 'dividendYield', value: `${((hashSeed(ticker) % 300) / 100).toFixed(2)}%` },
        { labelKey: 'turnover', value: `${((hashSeed(ticker) % 150) / 100).toFixed(2)}%` },
        { labelKey: 'week52Range', value: `${(basePrice * 1.2).toFixed(2)} / ${(basePrice * 0.65).toFixed(2)}` },
      ],
    ],
    kline: buildKline(ticker, basePrice, 60),
    peBand: buildPeBand(ticker),
    financials: [
      { year: '2019', revenue: 100, netProfit: 18, revenueYoY: 5.2 },
      { year: '2020', revenue: 112, netProfit: 21, revenueYoY: 12.0 },
      { year: '2021', revenue: 128, netProfit: 24, revenueYoY: 14.3 },
      { year: '2022', revenue: 141, netProfit: 26, revenueYoY: 10.2 },
      { year: '2023', revenue: 136, netProfit: 22, revenueYoY: -3.5 },
    ],
    profitability: [
      { key: 'grossMargin', value: 42, max: 60, percentile: 72, beatsLabelKey: 'beats72' },
      { key: 'netMargin', value: 18, max: 45, percentile: 68, beatsLabelKey: 'beats68' },
      { key: 'roe', value: 16, max: 35, percentile: 64, beatsLabelKey: 'beats64' },
      { key: 'roa', value: 9, max: 25, percentile: 58, beatsLabelKey: 'beats58' },
    ],
    analyst: {
      epsForecast: [
        { year: '2024E', eps: 2.4 },
        { year: '2025E', eps: 2.8 },
        { year: '2026E', eps: 3.1 },
      ],
      rating: { buy: 55, hold: 30, sell: 15 },
      targetPriceAvg: +(basePrice * 1.1).toFixed(2),
      targetPriceCurrent: basePrice,
      currency: market === 'us' ? 'USD' : market === 'hk' ? 'HKD' : 'CNY',
    },
    risk: {
      earningsDate: '2024-08-15',
      earningsDaysRemaining: 62,
      insiderTrades: [],
      noMajorWarnings: true,
    },
  };
}

export function getMockCoreAsset(ctx: CoreTickerContext): CoreAssetSnapshot {
  const ticker = normalizeTicker(ctx.ticker);
  if (ticker === 'TSM') {
    return {
      ...TSM_SNAPSHOT,
      market: ctx.market ?? TSM_SNAPSHOT.market,
      name: {
        zh: ctx.name_zh || TSM_SNAPSHOT.name.zh,
        en: ctx.name_en || TSM_SNAPSHOT.name.en,
      },
    };
  }
  return buildGenericSnapshot(ctx);
}
