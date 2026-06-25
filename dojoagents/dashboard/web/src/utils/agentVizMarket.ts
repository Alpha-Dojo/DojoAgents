import type { MarketCode } from '../types/dojoMesh';

export const AGENT_VIZ_MARKETS: MarketCode[] = ['us', 'cn', 'hk'];

export const AGENT_MARKET_LINE: Record<MarketCode, string> = {
  us: '#5eb8ff',
  cn: '#ff9f6b',
  hk: '#ffd166',
};

export const AGENT_MARKET_LABEL: Record<MarketCode, string> = {
  us: '#7ec8ff',
  cn: '#ffb088',
  hk: '#ffe08a',
};

/** Slice shades within a market donut (light → saturated). */
export const AGENT_MARKET_SLICE_SHADES: Record<MarketCode, string[]> = {
  us: ['#8ecfff', '#5eb8ff', '#3d9ae8', '#2b7fc7', '#1f6aaa'],
  cn: ['#ffc099', '#ff9f6b', '#f08045', '#d96830', '#c05522'],
  hk: ['#ffe08a', '#ffd166', '#e6b84d', '#cc9f38', '#b38628'],
};

export function normalizeAgentMarket(value: unknown): MarketCode | null {
  const raw = String(value ?? '').trim().toLowerCase();
  if (raw === 'us' || raw === 'cn' || raw === 'hk') return raw;
  if (raw === 'sh') return 'cn';
  return null;
}

export function agentMarketLineColor(market: unknown, fallbackIndex = 0): string {
  const code = normalizeAgentMarket(market);
  if (code) return AGENT_MARKET_LINE[code];
  const palette = ['#00e5ff', '#00e676', '#ff9800', '#ab47bc'];
  return palette[fallbackIndex % palette.length];
}

export function agentMarketSliceColor(market: unknown, index: number): string {
  const code = normalizeAgentMarket(market);
  if (code) {
    const shades = AGENT_MARKET_SLICE_SHADES[code];
    return shades[index % shades.length];
  }
  const palette = ['#00e5ff', '#00e676', '#ff9800', '#5c6bc0', '#26c6da', '#ab47bc'];
  return palette[index % palette.length];
}

export function isBenchmarkSeries(id: string): boolean {
  return id.startsWith('bench_');
}

export function seriesMarketId(id: string): MarketCode | null {
  if (isBenchmarkSeries(id)) {
    return normalizeAgentMarket(id.replace(/^bench_/, ''));
  }
  return normalizeAgentMarket(id);
}
