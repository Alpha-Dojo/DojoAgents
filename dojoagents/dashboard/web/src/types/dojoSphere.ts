import type { BilingualText, MarketCode } from '../types/dojoMesh';

export type SectorLevelKey = 'L1' | 'L2' | 'L3';
export type SphereMarketTab = MarketCode;

export interface SectorScopeMarketStats {
  market: MarketCode;
  member_count: number;
  total_market_cap: number;
  weighted_pe: number | null;
  pe_sample_count: number;
}

export interface SectorScopeMetricsResponse {
  level1_id: string;
  level2_id: string;
  level3_id: string;
  scopes: Record<SectorLevelKey, Partial<Record<MarketCode, SectorScopeMarketStats>>>;
}

export interface SectorConstituentItem {
  ticker: string;
  market: MarketCode;
  name: BilingualText;
  currency: string;
  last_price: number | null;
  change_percent: number | null;
  window_change_percent: number | null;
  turn_rate: number | null;
  market_cap: number | null;
  pe: number | null;
  pb: number | null;
  amount: number | null;
}

export interface SectorConstituentsResponse {
  level1_id: string;
  level2_id: string;
  level3_id: string;
  scope: SectorLevelKey;
  market: MarketCode | null;
  items: SectorConstituentItem[];
}

export type SpherePerformanceRange = '1D' | '5D' | '1M' | '1Y';

export interface SectorPerformancePoint {
  date: string;
  us?: number | null;
  cn?: number | null;
  hk?: number | null;
}

export interface SectorPerformanceMarketStats {
  cumulative_return_pct: number | null;
  sharpe_ratio: number | null;
  max_drawdown_pct: number | null;
  calmar_ratio: number | null;
  volatility_pct: number | null;
  trading_days: number;
}

export interface SectorPerformanceMarketPoint {
  date: string;
  value: number;
}

export interface SectorPerformanceResponse {
  level1_id: string;
  level2_id: string;
  level3_id: string;
  scope: SectorLevelKey;
  window_start: string | null;
  window_end: string | null;
  points: SectorPerformancePoint[];
  series_by_market: Partial<Record<MarketCode, SectorPerformanceMarketPoint[]>>;
  stats_by_market: Partial<Record<MarketCode, SectorPerformanceMarketStats>>;
  members_by_market: Partial<Record<MarketCode, number>>;
}
