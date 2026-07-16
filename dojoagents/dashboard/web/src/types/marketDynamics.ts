export type EventCategory =
  | 'geo_military'
  | 'geo_election'
  | 'geo_sanction'
  | 'macro_data'
  | 'macro_central_bank'
  | 'macro_fx_bond'
  | 'corporate_earnings'
  | 'corporate_ma'
  | 'industry_regulation'
  | 'industry_supply'
  | 'industry_price'
  | 'industry_tech'
  | 'market_structure'
  | 'institutional_view'
  | 'black_swan'
  | string;

export type SurpriseLevel = 'expected' | 'slight' | 'significant' | string;

export type ImpactDirection = 'Positive' | 'Negative' | 'Divergent' | string;

export interface DynamicsBilingualText {
  zh: string;
  en: string;
}

export interface MarketDynamicsSectorImpact {
  sector_id: string;
  sector_name: DynamicsBilingualText;
  affected_markets: string[];
  direction: ImpactDirection;
  reason: string;
}

export interface MarketDynamicsSummary {
  headline: DynamicsBilingualText;
  content: DynamicsBilingualText;
  source: DynamicsBilingualText;
  category: EventCategory;
  surprise: SurpriseLevel;
}

export interface MarketDynamicsEvent {
  id: string;
  event_time: string;
  trading_date: string;
  event_summary: MarketDynamicsSummary;
  sector_impacts: MarketDynamicsSectorImpact[];
}

export interface MarketDynamicsResponse {
  total_num: number;
  events: MarketDynamicsEvent[];
  window_start?: string;
  window_end?: string;
  dataset_start?: string;
  dataset_end?: string;
  has_more_before?: boolean;
  has_more_after?: boolean;
  trading_dates?: string[];
}

export const EVENT_CATEGORIES = [
  'market_structure',
  'corporate_earnings',
  'industry_tech',
  'industry_regulation',
  'industry_price',
  'geo_sanction',
  'macro_data',
  'geo_military',
  'industry_supply',
  'macro_central_bank',
  'macro_fx_bond',
  'institutional_view',
  'corporate_ma',
  'geo_election',
  'black_swan',
] as const;
