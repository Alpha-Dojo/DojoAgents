import type { ResolvedSectorPath } from '../types/sectorTaxonomy';

export type SectorMarketTab = 'all' | 'us' | 'cn' | 'hk';
export type SpherePerformanceRange = '1D' | '5D' | '1M' | '1Y';

export interface SphereFlowGauge {
  market: 'us' | 'cn' | 'hk';
  changePercent: number;
  inflowLabel: string;
}

export interface SpherePerformancePoint {
  date: string;
  us: number;
  cn: number;
  hk: number;
}

export interface SphereConstituentRow {
  ticker: string;
  market: 'us' | 'cn' | 'hk';
  nameZh: string;
  nameEn: string;
  lastPrice: number;
  currency: string;
  dayChange: number;
  fiveDayChange: number;
  volumeShare: number;
  growth: number;
  peg: number;
  roe: number;
  grossMargin: number;
  quantScore: number;
}

export interface SpherePageMock {
  heroTags: string[];
  totalMarketCapLabel: string;
  flowGauges: SphereFlowGauge[];
  performance: SpherePerformancePoint[];
  radar: { label: string; value: number }[];
  dupont: { label: string; value: number }[];
  riskScore: number;
  riskComponents: number;
  riskFlags: number;
  chainLabel: string;
  constituents: SphereConstituentRow[];
}

const MOCK_ROWS: SphereConstituentRow[] = [
  {
    ticker: 'AAPL',
    market: 'us',
    nameZh: '苹果',
    nameEn: 'Apple',
    lastPrice: 198.2,
    currency: 'USD',
    dayChange: 1.24,
    fiveDayChange: 3.8,
    volumeShare: 18,
    growth: 12.4,
    peg: 1.8,
    roe: 42.1,
    grossMargin: 44.2,
    quantScore: 5,
  },
  {
    ticker: '000333.SZ',
    market: 'cn',
    nameZh: '美的集团',
    nameEn: 'Midea Group',
    lastPrice: 68.5,
    currency: 'CNY',
    dayChange: -0.42,
    fiveDayChange: 1.1,
    volumeShare: 12,
    growth: 9.6,
    peg: 1.2,
    roe: 18.4,
    grossMargin: 28.6,
    quantScore: 4,
  },
  {
    ticker: '1810.HK',
    market: 'hk',
    nameZh: '小米集团',
    nameEn: 'Xiaomi',
    lastPrice: 18.76,
    currency: 'HKD',
    dayChange: 2.05,
    fiveDayChange: 4.6,
    volumeShare: 15,
    growth: 15.2,
    peg: 1.5,
    roe: 16.8,
    grossMargin: 21.3,
    quantScore: 4,
  },
  {
    ticker: 'GOOGL',
    market: 'us',
    nameZh: '谷歌',
    nameEn: 'Alphabet',
    lastPrice: 176.4,
    currency: 'USD',
    dayChange: 0.88,
    fiveDayChange: 2.3,
    volumeShare: 10,
    growth: 11.1,
    peg: 1.6,
    roe: 28.5,
    grossMargin: 56.1,
    quantScore: 5,
  },
  {
    ticker: 'NVDA',
    market: 'us',
    nameZh: '英伟达',
    nameEn: 'NVIDIA',
    lastPrice: 892.1,
    currency: 'USD',
    dayChange: 2.44,
    fiveDayChange: 6.2,
    volumeShare: 14,
    growth: 22.8,
    peg: 2.4,
    roe: 69.2,
    grossMargin: 72.7,
    quantScore: 5,
  },
  {
    ticker: '002371.SZ',
    market: 'cn',
    nameZh: '北方华创',
    nameEn: 'NAURA',
    lastPrice: 312.6,
    currency: 'CNY',
    dayChange: 1.05,
    fiveDayChange: 2.8,
    volumeShare: 9,
    growth: 19.4,
    peg: 1.9,
    roe: 16.2,
    grossMargin: 41.5,
    quantScore: 4,
  },
  {
    ticker: '0981.HK',
    market: 'hk',
    nameZh: '中芯国际',
    nameEn: 'SMIC',
    lastPrice: 16.42,
    currency: 'HKD',
    dayChange: -0.66,
    fiveDayChange: -1.2,
    volumeShare: 11,
    growth: 14.1,
    peg: 2.2,
    roe: 8.6,
    grossMargin: 18.9,
    quantScore: 3,
  },
  {
    ticker: 'TSM',
    market: 'us',
    nameZh: '台积电',
    nameEn: 'TSMC',
    lastPrice: 142.8,
    currency: 'USD',
    dayChange: 0.52,
    fiveDayChange: 1.9,
    volumeShare: 13,
    growth: 16.7,
    peg: 1.7,
    roe: 26.3,
    grossMargin: 53.4,
    quantScore: 5,
  },
  {
    ticker: '688981.SH',
    market: 'cn',
    nameZh: '中芯国际',
    nameEn: 'SMIC A',
    lastPrice: 48.9,
    currency: 'CNY',
    dayChange: -0.31,
    fiveDayChange: 0.6,
    volumeShare: 7,
    growth: 13.2,
    peg: 2.0,
    roe: 7.8,
    grossMargin: 17.6,
    quantScore: 3,
  },
  {
    ticker: 'AMD',
    market: 'us',
    nameZh: '超威半导体',
    nameEn: 'AMD',
    lastPrice: 164.3,
    currency: 'USD',
    dayChange: 1.76,
    fiveDayChange: 4.1,
    volumeShare: 8,
    growth: 18.9,
    peg: 2.3,
    roe: 4.2,
    grossMargin: 50.8,
    quantScore: 4,
  },
  {
    ticker: '1347.HK',
    market: 'hk',
    nameZh: '华虹半导体',
    nameEn: 'Hua Hong',
    lastPrice: 22.15,
    currency: 'HKD',
    dayChange: 0.92,
    fiveDayChange: 2.5,
    volumeShare: 6,
    growth: 11.8,
    peg: 1.4,
    roe: 9.1,
    grossMargin: 22.4,
    quantScore: 4,
  },
];

function buildPerformanceSeries(): SpherePerformancePoint[] {
  const points: SpherePerformancePoint[] = [];
  let us = 100;
  let cn = 100;
  let hk = 100;
  for (let i = 0; i < 12; i += 1) {
    us += (Math.sin(i / 2) + 0.2) * 2.4;
    cn += (Math.cos(i / 3) + 0.1) * 2.1;
    hk += (Math.sin(i / 4) - 0.05) * 1.8;
    points.push({
      date: `2025-${String(i + 1).padStart(2, '0')}-05`,
      us: Number(us.toFixed(2)),
      cn: Number(cn.toFixed(2)),
      hk: Number(hk.toFixed(2)),
    });
  }
  return points;
}

export function buildSphereMock(path: ResolvedSectorPath): SpherePageMock {
  const l3En = path.level3.name.en;
  return {
    heroTags: ['高景气', '拥挤度: 85%'],
    totalMarketCapLabel: '$1.8T (Global 加权)',
    flowGauges: [
      { market: 'us', changePercent: 1.1, inflowLabel: '+$200M Inflow' },
      { market: 'cn', changePercent: -0.8, inflowLabel: '-¥1.2B Inflow' },
      { market: 'hk', changePercent: 0.4, inflowLabel: '+HK$80M Inflow' },
    ],
    performance: buildPerformanceSeries(),
    radar: [
      { label: 'Profitability', value: 78 },
      { label: 'Growth', value: 72 },
      { label: 'Quality', value: 66 },
      { label: 'Momentum', value: 61 },
      { label: 'Valuation', value: 54 },
    ],
    dupont: [
      { label: '1yr', value: 18 },
      { label: '3yr', value: 20 },
      { label: '5yr', value: 22 },
    ],
    riskScore: 68,
    riskComponents: 120,
    riskFlags: 15,
    chainLabel: `${l3En} · Midstream / 下游占比提升`,
    constituents: MOCK_ROWS.slice(0, 8),
  };
}
