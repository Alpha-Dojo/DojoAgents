import type { MarketCode } from '../types/market';
import { DATA_START_DATE } from '../utils/klineDate';

export type FolioPortfolioKind = 'manual' | 'agent';

export type FolioAllocationStrategy = 'equal_weight' | 'market_cap' | 'risk_parity';

export interface FolioHolding {
  ticker: string;
  name: string;
  market: MarketCode;
  shares: number;
  weight: number;
  cost: number;
  costLow?: number;
  costHigh?: number;
  usesDefaultCost?: boolean;
  costDate?: string;
  costBasis: number;
  openDate?: string;
  usesDefaultOpenDate?: boolean;
  sharesLocked?: boolean;
  openDateLocked?: boolean;
  costLocked?: boolean;
  manualShares?: boolean;
  nameZh?: string;
  nameEn?: string;
  price: number;
  changePercent: number;
  totalReturnPct: number | null;
  sector: string;
  sectorL1?: string;
  sectorL2?: string;
  sectorL3?: string;
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

export interface FolioPerformancePoint {
  date: string;
  value: number;
}

export interface FolioPerformanceStats {
  cumulative_return_pct: number | null;
  volatility_pct: number | null;
  sharpe_ratio: number | null;
  calmar_ratio: number | null;
  max_drawdown_pct: number | null;
  trading_days: number;
}

export interface FolioPerformanceView {
  windowStart?: string | null;
  windowEnd?: string | null;
  seriesByMarket: Partial<Record<MarketCode, FolioPerformancePoint[]>>;
  benchmarkByMarket: Partial<Record<MarketCode, FolioPerformancePoint[]>>;
  benchmarkSymbolByMarket: Partial<Record<MarketCode, string>>;
  statsByMarket: Partial<Record<MarketCode, FolioPerformanceStats>>;
}

/** @deprecated legacy flat series shape */
export interface FolioPerformanceSeries {
  dates: string[];
  portfolio: number[];
  benchmark: number[];
}

export const FOLIO_MARKETS: MarketCode[] = ['us', 'cn', 'hk'];

export const DEFAULT_FOLIO_CONFIG: FolioPortfolioConfig = {
  startDate: DATA_START_DATE,
  costDate: DATA_START_DATE,
  capitalByMarket: {
    us: 1_000_000,
    cn: 1_000_000,
    hk: 1_000_000,
  },
};
