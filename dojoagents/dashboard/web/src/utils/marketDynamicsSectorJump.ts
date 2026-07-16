import type { MarketCode, SectorItem } from '../types/market';
import type { MarketDynamicsSectorImpact } from '../types/marketDynamics';
import type { SectorPathSelection, SectorTaxonomyDocument } from '../types/sectorTaxonomy';
import { DEFAULT_MARKET_ORDER } from '../navigation/marketColumnOrder';
import {
  findSectorPathByIds,
  findSectorPathByL3Name,
  slugifySectorLabel,
} from './sectorTaxonomy';

function toMarketCode(raw: string): MarketCode | null {
  const key = String(raw || '')
    .trim()
    .toLowerCase();
  if (key === 'us' || key === 'cn' || key === 'hk') return key;
  if (key === 'sh' || key === 'sz' || key === 'a' || key === 'ashare') return 'cn';
  return null;
}

/** Dynamics `sector_id` is typically `level1_id/level2_id/level3_id`. */
export function parseDynamicsSectorId(sectorId: string): SectorPathSelection | null {
  const parts = String(sectorId || '')
    .split('/')
    .map((part) => part.trim())
    .filter(Boolean);
  if (parts.length < 3) return null;
  return {
    level1Id: parts[0],
    level2Id: parts[1],
    level3Id: parts[2],
  };
}

/** Prefer Market-page column order among affected markets. */
export function preferredImpactMarket(
  markets: string[] | undefined,
  marketOrder: MarketCode[] = DEFAULT_MARKET_ORDER,
): MarketCode {
  const codes = [
    ...new Set(
      (markets ?? [])
        .map(toMarketCode)
        .filter((code): code is MarketCode => code != null),
    ),
  ];
  for (const code of marketOrder) {
    if (codes.includes(code)) return code;
  }
  return codes[0] ?? marketOrder[0] ?? 'us';
}

/**
 * Build a SectorItem so MarketPage can reuse the same sector-discovery jump path
 * as Treemap / movers rows.
 */
export function dynamicsImpactToSectorItem(
  impact: MarketDynamicsSectorImpact,
  market: MarketCode,
  taxonomy: SectorTaxonomyDocument | null,
): SectorItem | null {
  const selection = parseDynamicsSectorId(impact.sector_id);
  let path =
    selection && taxonomy ? findSectorPathByIds(taxonomy, selection) : null;
  if (!path && taxonomy) {
    path = findSectorPathByL3Name(
      taxonomy,
      impact.sector_name?.zh ?? '',
      impact.sector_name?.en ?? '',
    );
  }

  const nameZh = (impact.sector_name?.zh || path?.level3.name.zh || '').trim();
  const nameEn = (impact.sector_name?.en || path?.level3.name.en || '').trim();
  const linkKey =
    slugifySectorLabel(nameEn || nameZh) ||
    (path ? slugifySectorLabel(path.level3.name.en) : '');
  if (!linkKey && !nameZh && !nameEn) return null;

  return {
    concept_code: `${market.toUpperCase()}.L3.${linkKey || 'unknown'}`,
    name: { zh: nameZh, en: nameEn },
    change_percent: 0,
    strength: 0,
    sample_tickers: [],
    level1_id: path?.level1.id ?? selection?.level1Id,
    level2_id: path?.level2.id ?? selection?.level2Id,
    level3_id: path?.level3.id ?? selection?.level3Id,
  };
}
