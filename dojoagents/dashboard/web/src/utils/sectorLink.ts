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
}

/** undefined = loading, null = not found, SectorItem = resolved */
export type CrossMarketLookup = Partial<Record<MarketCode, SectorItem | null | undefined>>;

function sectorVariant(changePercent: number): 'gain' | 'loss' {
  return changePercent >= 0 ? 'gain' : 'loss';
}

function sectorLeadSortScore(sector: SectorItem): number {
  return (sector.avg_market_cap ?? 0) * sector.change_percent;
}

function withStrength(sector: SectorItem, peers: SectorItem[]): SectorItem {
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

function mapRows(
  sectors: SectorItem[],
  link: CrossMarketLink,
  market: MarketCode,
  mapRow: (sector: SectorItem) => Omit<OrderedSectorRow, 'sector'>,
): OrderedSectorRow[] {
  return sectors.map((sector) => ({
    sector,
    ...mapRow(sector),
    selected: market === link.sourceMarket && sector.concept_code === link.sourceConceptCode,
  }));
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

  if (isSource) {
    if (!inList) {
      return mapRows(sectors, link, market, () => ({}));
    }
    const rest = sectors.filter((s) => sectorLinkKey(s.concept_code) !== link.linkKey);
    return [
      {
        sector: inList,
        selected: inList.concept_code === link.sourceConceptCode,
      },
      ...mapRows(rest, link, market, () => ({})),
    ];
  }

  if (inList) {
    const rest = sectors.filter((s) => sectorLinkKey(s.concept_code) !== link.linkKey);
    return [
      { sector: inList, linked: true },
      ...mapRows(rest, link, market, () => ({})),
    ];
  }

  if (lookupSector === undefined) {
    return mapRows(sectors, link, market, () => ({}));
  }

  let pinned: SectorItem | null = null;
  let missing = false;

  if (lookupSector) {
    if (sectorVariant(lookupSector.change_percent) !== variant) {
      return mapRows(sectors, link, market, () => ({}));
    }
    pinned = withStrength(lookupSector, sectors);
  } else {
    if (sectorVariant(link.sourceChangePercent) !== variant) {
      return mapRows(sectors, link, market, () => ({}));
    }
    missing = true;
    pinned = {
      concept_code: `${market.toUpperCase()}.L3.${link.linkKey}`,
      name: link.sourceName,
      change_percent: 0,
      strength: 0,
      sample_tickers: [],
      member_count: 0,
      members: [],
    };
  }

  return [
    {
      sector: pinned,
      linked: true,
      injected: true,
      missing,
    },
    ...mapRows(sectors, link, market, () => ({})),
  ];
}
