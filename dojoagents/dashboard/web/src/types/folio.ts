import type { MarketCode } from '../types/market';
import { FOLIO_DEFAULT_START_DATE } from '../utils/klineDate';

export type FolioPortfolioKind = 'manual' | 'agent';

export type FolioAllocationStrategy = 'equal_weight' | 'market_cap' | 'risk_parity';

export interface FolioCandidate {
  ticker: string;
  name: string;
  nameZh?: string;
  nameEn?: string;
  market: MarketCode;
  price: number;
  changePercent: number;
  marketCap: number;
  pe: number | null;
  pb: number | null;
  dividendYield: number | null;
  eps: number | null;
  turnRate: number | null;
  sector: string;
  sectorL1?: string;
  sectorL2?: string;
  sectorL3?: string;
}

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

export type FolioOrderSide = 'buy' | 'sell';

export type FolioOrderStatus = 'pending' | 'filled' | 'cancelled' | 'rejected';

export interface FolioOrder {
  id: string;
  ticker: string;
  name: string;
  nameZh?: string;
  nameEn?: string;
  market: MarketCode;
  orderSide: FolioOrderSide;
  orderStatus: FolioOrderStatus;
  price: number;
  qty: number;
  orderTime?: string;
  fillTime?: string;
  fillPrice?: number | null;
  createdAt: string;
}

export interface FolioCreateOrderPayload {
  ticker: string;
  market: MarketCode;
  orderSide: FolioOrderSide;
  price: number;
  qty: number;
  orderTime?: string | null;
}

export interface FolioOrderDraftContext {
  market: MarketCode;
  ticker?: string;
  price?: number;
  name?: string;
  orderSide?: FolioOrderSide;
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
  candidateSeriesByMarket?: Partial<Record<MarketCode, FolioPerformancePoint[]>>;
  benchmarkByMarket: Partial<Record<MarketCode, FolioPerformancePoint[]>>;
  benchmarkSymbolByMarket: Partial<Record<MarketCode, string>>;
  statsByMarket: Partial<Record<MarketCode, FolioPerformanceStats>>;
  candidateStatsByMarket?: Partial<Record<MarketCode, FolioPerformanceStats>>;
}

/** @deprecated legacy flat series shape */
export interface FolioPerformanceSeries {
  dates: string[];
  portfolio: number[];
  benchmark: number[];
}

export const FOLIO_MARKETS: MarketCode[] = ['us', 'cn', 'hk'];

export const DEFAULT_FOLIO_CONFIG: FolioPortfolioConfig = {
  startDate: FOLIO_DEFAULT_START_DATE,
  costDate: FOLIO_DEFAULT_START_DATE,
  capitalByMarket: {
    us: 1_000_000,
    cn: 1_000_000,
    hk: 1_000_000,
  },
};
