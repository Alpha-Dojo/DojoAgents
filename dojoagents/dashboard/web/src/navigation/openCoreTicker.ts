import type { MarketCode } from '../types/dojoMesh';
import type { AppTab } from './appTab';
import type { CoreSectorSource, CoreTickerContext } from './coreContext';
import { saveCoreTickerContext } from './coreContext';
import type { SectorPathSelection } from '../types/sectorTaxonomy';

export interface OpenCoreTickerPayload {
  ticker: string;
  market?: MarketCode;
  name_zh?: string;
  name_en?: string;
  sector_source?: CoreSectorSource;
  sector_selection?: SectorPathSelection;
}

export function openCoreTicker(
  navigate: ((tab: AppTab) => void) | undefined,
  payload: OpenCoreTickerPayload,
) {
  const ctx: CoreTickerContext = {
    ticker: payload.ticker,
    market: payload.market,
    name_zh: payload.name_zh,
    name_en: payload.name_en,
    sector_source: payload.sector_source,
    sector_selection: payload.sector_selection,
  };
  saveCoreTickerContext(ctx);
  navigate?.('core');
}
