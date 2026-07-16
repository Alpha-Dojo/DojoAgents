import { hierarchy, treemap, treemapSquarify, type HierarchyRectangularNode } from 'd3-hierarchy';
import type { MarketCode, SectorItem } from '../types/market';

export const TREEMAP_TOP_N = 10;
export const TREEMAP_HEIGHT = 280;
export const TREEMAP_INNER_PAD = 3;

export interface MarketSectorMove extends SectorItem {
  market: MarketCode;
}

export interface TreemapRect {
  move: MarketSectorMove;
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface SingleMarketTreemapLayout {
  width: number;
  height: number;
  market: MarketCode;
  rects: TreemapRect[];
}

interface TreemapLeafDatum {
  move: MarketSectorMove;
  value: number;
}

interface TreemapMarketDatum {
  market: MarketCode;
  children: TreemapLeafDatum[];
}

interface TreemapRootDatum {
  children: TreemapMarketDatum[];
}

type TreemapDatum = TreemapRootDatum | TreemapMarketDatum | TreemapLeafDatum;

export type TreemapLabelTier = 'full' | 'pct' | 'none';

function isTreemapLeaf(datum: TreemapDatum): datum is TreemapLeafDatum {
  return 'move' in datum;
}

/**
 * Tile area / ranking among cap-eligible sectors.
 * Market cap is applied upstream as a floor filter; ranking uses |change%| only
 * so Daily Discovery stays aligned with Sector Movers list order.
 */
export function treemapWeight(move: MarketSectorMove): number {
  return Math.max(Math.abs(move.change_percent), 0.01);
}

export function topMovesForMarketByAbsChange(
  moves: MarketSectorMove[],
  count: number,
): MarketSectorMove[] {
  return [...moves]
    .sort((a, b) => Math.abs(b.change_percent) - Math.abs(a.change_percent))
    .slice(0, count);
}

export function treemapHeatFill(changePercent: number, maxAbs: number): string {
  const ratio = Math.min(Math.abs(changePercent) / maxAbs, 1);
  if (changePercent > 0) {
    const r = Math.round(28 - ratio * 12);
    const g = Math.round(118 + ratio * 93);
    const b = Math.round(72 + ratio * 28);
    return `rgb(${r} ${g} ${b})`;
  }
  if (changePercent < 0) {
    const r = Math.round(168 + ratio * 80);
    const g = Math.round(58 - ratio * 28);
    const b = Math.round(58 - ratio * 18);
    return `rgb(${r} ${g} ${b})`;
  }
  return 'rgb(72 82 96)';
}

export function treemapLabelTier(w: number, h: number): TreemapLabelTier {
  const area = w * h;
  if (w >= 48 && h >= 28 && area >= 900) return 'full';
  if (w >= 24 && h >= 18 && area >= 320) return 'pct';
  return 'none';
}

export function formatPct(changePercent: number): string {
  const up = changePercent >= 0;
  return `${up ? '+' : ''}${changePercent.toFixed(2)}%`;
}

export function abbreviateLabel(label: string, max = 10): string {
  if (label.length <= max) return label;
  return `${label.slice(0, max - 1)}…`;
}

function layoutTreemapLeaves(
  leaves: TreemapLeafDatum[],
  originX: number,
  originY: number,
  areaWidth: number,
  areaHeight: number,
): TreemapRect[] {
  if (leaves.length === 0 || areaWidth <= 0 || areaHeight <= 0) return [];

  const root = hierarchy<TreemapDatum>({ children: [{ market: 'us', children: leaves }] })
    .sum((datum) => (isTreemapLeaf(datum) ? datum.value : 0))
    .sort((a, b) => (b.value ?? 0) - (a.value ?? 0));

  treemap<TreemapDatum>()
    .tile(treemapSquarify.ratio(1.12))
    .size([areaWidth, areaHeight])
    .paddingInner(3)
    .round(true)(root);

  const layoutRoot = root as HierarchyRectangularNode<TreemapDatum>;
  const marketNode = layoutRoot.children?.[0];

  return (marketNode?.leaves() ?? []).map((leaf) => {
    const leafDatum = leaf.data as TreemapLeafDatum;
    return {
      move: leafDatum.move,
      x: originX + leaf.x0,
      y: originY + leaf.y0,
      w: Math.max(leaf.x1 - leaf.x0, 0),
      h: Math.max(leaf.y1 - leaf.y0, 0),
    };
  });
}

export function layoutSingleMarketTreemap(
  moves: MarketSectorMove[],
  market: MarketCode,
  width: number,
  height = TREEMAP_HEIGHT,
  topN = TREEMAP_TOP_N,
): SingleMarketTreemapLayout | null {
  if (width <= 0 || height <= 0) return null;

  const pad = TREEMAP_INNER_PAD;
  const leaves: TreemapLeafDatum[] = topMovesForMarketByAbsChange(
    moves.filter((move) => move.market === market),
    topN,
  ).map((move) => ({
    move,
    value: treemapWeight(move),
  }));

  if (leaves.length === 0) {
    return { width, height, market, rects: [] };
  }

  const rects = layoutTreemapLeaves(
    leaves,
    pad,
    pad,
    width - pad * 2,
    height - pad * 2,
  );

  return { width, height, market, rects };
}

export function mergeMarketMovers(
  markets: Partial<
    Record<MarketCode, { gainers: SectorItem[]; losers: SectorItem[] }>
  >,
): MarketSectorMove[] {
  const byKey = new Map<string, MarketSectorMove>();
  for (const market of ['us', 'cn', 'hk'] as MarketCode[]) {
    const payload = markets[market];
    if (!payload) continue;
    for (const item of [...(payload.gainers ?? []), ...(payload.losers ?? [])]) {
      const key = `${market}:${item.concept_code}`;
      if (!byKey.has(key)) {
        byKey.set(key, { ...item, market });
      }
    }
  }
  return [...byKey.values()];
}
