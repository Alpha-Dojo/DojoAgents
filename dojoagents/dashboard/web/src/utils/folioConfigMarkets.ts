import { FOLIO_MARKETS } from '../types/folio';
import type { MarketCode } from '../types/market';

interface FolioMarketEntry {
  market: MarketCode;
}

interface FolioConfigMarketSource {
  positions: FolioMarketEntry[];
  candidates: FolioMarketEntry[];
}

interface FolioMarketSnapshotSource {
  candidateCount: number;
  holdingCount: number;
}

export function resolveFolioConfigMarkets(source: FolioConfigMarketSource): MarketCode[] {
  const presentMarkets = new Set<MarketCode>();

  for (const row of source.positions) {
    presentMarkets.add(row.market);
  }
  for (const row of source.candidates) {
    presentMarkets.add(row.market);
  }

  if (presentMarkets.size === 0) return FOLIO_MARKETS;
  return FOLIO_MARKETS.filter((market) => presentMarkets.has(market));
}

export function resolveFolioSnapshotMarkets(
  snapshots: Partial<Record<MarketCode, FolioMarketSnapshotSource>> | undefined,
): MarketCode[] {
  if (!snapshots) return FOLIO_MARKETS;

  const markets = FOLIO_MARKETS.filter((market) => {
    const snapshot = snapshots[market];
    return (snapshot?.candidateCount ?? 0) > 0 || (snapshot?.holdingCount ?? 0) > 0;
  });

  return markets.length > 0 ? markets : FOLIO_MARKETS;
}
