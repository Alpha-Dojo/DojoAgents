import type { MarketCode } from '../types/market';
import type { AppTab } from './appTab';
import type { EntitySectorSource, EntityTickerContext } from './entityContext';
import { saveEntityTickerContext } from './entityContext';
import type { SectorPathSelection } from '../types/sectorTaxonomy';

export interface OpenCoreTickerPayload {
  ticker: string;
  market?: MarketCode;
  name_zh?: string;
  name_en?: string;
  sector_source?: EntitySectorSource;
  sector_selection?: SectorPathSelection;
}

export function openEntityTicker(
  navigate: ((tab: AppTab) => void) | undefined,
  payload: OpenCoreTickerPayload,
) {
  const ctx: EntityTickerContext = {
    ticker: payload.ticker,
    market: payload.market,
    name_zh: payload.name_zh,
    name_en: payload.name_en,
    sector_source: payload.sector_source,
    sector_selection: payload.sector_selection,
  };
  saveEntityTickerContext(ctx);
  navigate?.('entity');
}
