import type { BilingualText, MarketCode, SectorItem } from '../types/dojoMesh';

/** Stable cross-market key from level-3 English slug in concept_code. */
export function sectorLinkKey(conceptCode: string): string | null {
  const match = conceptCode.match(/\.L3\.(.+)$/i);
  return match?.[1] ?? null;
}

export interface CrossMarketLink {
  linkKey: string;
  sourceMarket: MarketCode;
  sourceConceptCode: string;
  sourceName: BilingualText;
  sourceChangePercent: number;
}

export interface OrderedSectorRow {
  sector: SectorItem;
  linked?: boolean;
  selected?: boolean;
  injected?: boolean;
  missing?: boolean;
  /** Scroll this row into view inside the sector list (cross-market highlight). */
  scrollIntoView?: boolean;
}

/** undefined = loading, null = not found, SectorItem = resolved */
export type CrossMarketLookup = Partial<Record<MarketCode, SectorItem | null | undefined>>;

function sectorVariant(changePercent: number): 'gain' | 'loss' {
  return changePercent >= 0 ? 'gain' : 'loss';
}

function sectorLeadSortScore(sector: SectorItem): number {
  return (sector.avg_market_cap ?? 0) * (sector.change_percent ?? 0);
}

export function withStrength(sector: SectorItem, peers: SectorItem[]): SectorItem {
  const maxAbs = Math.max(
    ...peers.map((s) => Math.abs(sectorLeadSortScore(s))),
    Math.abs(sectorLeadSortScore(sector)),
    1,
  );
  return {
    ...sector,
    strength: Math.round((Math.abs(sectorLeadSortScore(sector)) / maxAbs) * 1000) / 10,
  };
}

function isSelectedSector(
  sector: SectorItem,
  link: CrossMarketLink,
  market: MarketCode,
): boolean {
  if (market === link.sourceMarket) {
    return sector.concept_code === link.sourceConceptCode;
  }
  return sectorLinkKey(sector.concept_code) === link.linkKey;
}

export function orderSectorsWithLink(
  sectors: SectorItem[],
  variant: 'gain' | 'loss',
  link: CrossMarketLink | null,
  market: MarketCode,
  lookupSector?: SectorItem | null | undefined,
): OrderedSectorRow[] {
  if (!link) {
    return sectors.map((sector) => ({ sector }));
  }

  const isSource = market === link.sourceMarket;
  const inList = sectors.find((s) => sectorLinkKey(s.concept_code) === link.linkKey);

  if (inList || isSource) {
    return sectors.map((sector) => {
      const selected = isSelectedSector(sector, link, market);
      return {
        sector,
        selected,
        scrollIntoView: selected && !isSource,
      };
    });
  }

  if (lookupSector === undefined) {
    return sectors.map((sector) => ({ sector }));
  }

  if (!lookupSector || sectorVariant(lookupSector.change_percent) !== variant) {
    return sectors.map((sector) => ({ sector }));
  }

  return [
    ...sectors.map((sector) => ({ sector })),
    {
      sector: withStrength(lookupSector, sectors),
      selected: true,
      injected: true,
      scrollIntoView: true,
    },
  ];
}
