// QuantContext types

export type MarketType = 'stock' | 'crypto'

export interface QuantContext {
  market: MarketType
  symbols: string[]
  timeframe: string
  currency?: string
  data_freshness?: string
}
