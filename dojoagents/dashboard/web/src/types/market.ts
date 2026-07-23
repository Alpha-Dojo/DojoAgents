/** Backend market codes: cn, hk, us. */
export type MarketCode = 'us' | 'cn' | 'hk';

export interface BilingualText {
  en: string;
  zh: string;
}

/** Aggregate exchange statistics for one market column header. */
export interface MarketStats {
  market: MarketCode;
  listed_count: number;
  total_market_cap: number;
  weighted_pe: number | null;
  simple_pe: number | null;
  pe_sample_count: number;
}

/** One daily bar for benchmark sparkline. */
export interface BenchmarkKlinePoint {
  datetime: string;
  close: number;
}

/** Top index card per market column. */
export interface BenchmarkCard {
  market: MarketCode;
  symbol: string;
  name: BilingualText;
  price: number;
  change_percent: number;
  /** Daily bars, oldest → newest (for sparkline + hover). */
  kline: BenchmarkKlinePoint[];
}

/** One constituent in a sector row expand panel. */
export interface SectorMemberItem {
  ticker: string;
  name?: BilingualText;
  last_price?: number;
  market_cap?: number;
  change_percent: number;
}

/** One sector row in 领涨 / 领跌 lists. */
export interface SectorItem {
  concept_code: string;
  name: BilingualText;
  change_percent: number;
  /** Backend taxonomy path ids (numeric strings from API). */
  level1_id?: string;
  level2_id?: string;
  level3_id?: string;
  /** Average market cap of constituents; used with change_percent for lead/lag ranking. */
  avg_market_cap?: number;
  /** 0–100, relative bar width within the same list. */
  strength: number;
  /** Up to 3 representative tickers. */
  sample_tickers: string[];
  member_count?: number;
  members?: SectorMemberItem[];
  /** Top contributor by |weight × return| share of sector return. */
  leader_ticker?: string | null;
  leader_weight_pct?: number | null;
  leader_return_pct?: number | null;
  leader_contribution_pct?: number | null;
  leader_concentration_pct?: number | null;
  leader_concentration_tier?: 'extreme' | 'moderate' | 'healthy' | null;
}

export interface MarketColumn {
  stats: MarketStats;
  /** Selectable indices for this market column. */
  benchmarks: BenchmarkCard[];
  /** Initial selection; defaults to first benchmark. */
  default_benchmark?: string;
  gainers: SectorItem[];
  losers: SectorItem[];
}

/**
 * GET /api/v1/dojo-mesh/overview
 *
 * Aggregated payload for the market overview landing grid (US / A股 / HK).
 */
export interface MarketOverview {
  /** Trading date, e.g. "2026-05-29". */
  as_of: string;
  markets: Record<MarketCode, MarketColumn>;
}

export interface MarketOverviewQuery {
  /** Max sectors per gain/loss list; default 5. */
  sector_limit?: number;
  /** Lookback window in trading days for sector movers. */
  days?: number;
  /** Minimum total sector market cap per market (absolute currency units). */
  min_cap_by_market?: Partial<Record<MarketCode, number>>;
}
