import type { MarketCode } from '../types/dojoMesh';
import { oneYearAgoDate } from '../utils/folioStartDate';

export type FolioPortfolioKind = 'manual' | 'agent';

export interface FolioHolding {
  ticker: string;
  name: string;
  market: MarketCode;
  shares: number;
  weight: number;
  cost: number;
  openDate?: string;
  usesDefaultOpenDate?: boolean;
  manualShares?: boolean;
  price: number;
  changePercent: number;
  sector: string;
  marketValue: number;
}

export interface FolioPortfolioConfig {
  startDate: string;
  costDate: string;
  capitalByMarket: Record<MarketCode, number>;
}

export interface FolioKpiMetric {
  key: 'netValue' | 'cumulativeReturn' | 'sharpe' | 'maxDrawdown';
  value: string;
  delta?: string;
  deltaTone?: 'positive' | 'negative' | 'neutral' | 'risk';
  hint?: string;
}

export interface FolioPerformanceSeries {
  dates: string[];
  portfolio: number[];
  benchmark: number[];
}

export const FOLIO_MARKETS: MarketCode[] = ['us', 'sh', 'hk'];

export const DEFAULT_FOLIO_CONFIG: FolioPortfolioConfig = {
  startDate: defaultStartDate(),
  costDate: defaultStartDate(),
  capitalByMarket: {
    us: 1_000_000,
    sh: 1_000_000,
    hk: 1_000_000,
  },
};

function defaultStartDate(): string {
  return oneYearAgoDate();
}
