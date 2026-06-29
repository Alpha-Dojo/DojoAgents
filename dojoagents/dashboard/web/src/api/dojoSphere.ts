import { fetchJson } from './http';
import { dedupeFetch } from './adapters/cache';
import {
  type AlphaSectorAnalysis,
  type AlphaTaxonomyTree,
  mapSectorConstituents,
  mapSectorMetrics,
  mapSectorPerformance,
  mapSectorPerformanceByScope,
  transformTaxonomy,
} from './adapters/transforms';
import type { MarketCode } from '../types/dojoMesh';
import type {
  SectorConstituentsResponse,
  SectorLevelKey,
  SectorPerformanceResponse,
  SectorScopeMetricsResponse,
} from '../types/dojoSphere';
import type { SectorTaxonomyDocument } from '../types/sectorTaxonomy';

const API_PREFIX = '/api/v1';

function analysisCacheKey(params: {
  level1Id: string;
  level2Id: string;
  level3Id: string;
  scope: SectorLevelKey;
}) {
  return `${params.level1Id}:${params.level2Id}:${params.level3Id}:${params.scope}`;
}

function fetchSectorAnalysisRaw(params: {
  level1Id: string;
  level2Id: string;
  level3Id: string;
  scope: SectorLevelKey;
}): Promise<AlphaSectorAnalysis> {
  const query = new URLSearchParams({
    level1_id: params.level1Id,
    level2_id: params.level2Id,
    level3_id: params.level3Id,
    scope: params.scope,
  });
  return dedupeFetch(analysisCacheKey(params), () =>
    fetchJson<AlphaSectorAnalysis>(`${API_PREFIX}/sector/analysis?${query}`),
  );
}

export interface SectorAnalysisBundle {
  metrics: SectorScopeMetricsResponse;
  performanceByLevel: Partial<Record<SectorLevelKey, SectorPerformanceResponse>>;
}

/** Single sector/analysis call — metrics + L1/L2/L3 performance curves. */
export async function fetchSectorAnalysisBundle(params: {
  level1Id: string;
  level2Id: string;
  level3Id: string;
}): Promise<SectorAnalysisBundle> {
  const raw = await fetchSectorAnalysisRaw({ ...params, scope: 'L3' });
  return {
    metrics: mapSectorMetrics(raw),
    performanceByLevel: mapSectorPerformanceByScope(raw),
  };
}

/** Sector L1/L2/L3 tree from AlphaDojo utility taxonomy endpoint. */
export async function fetchSectorTaxonomy(): Promise<SectorTaxonomyDocument> {
  const raw = await fetchJson<AlphaTaxonomyTree>(`${API_PREFIX}/utility/taxonomy/tree`);
  return transformTaxonomy(raw);
}

/** Lightweight sector metrics (no L1/L2/L3 performance curves). */
export async function fetchDojoSphereSectorMetrics(params: {
  level1Id: string;
  level2Id: string;
  level3Id: string;
}): Promise<SectorScopeMetricsResponse> {
  const query = new URLSearchParams({
    level1_id: params.level1Id,
    level2_id: params.level2Id,
    level3_id: params.level3Id,
  });
  const raw = await fetchJson<{
    level1_id: string;
    level2_id: string;
    level3_id: string;
    scopes: Record<
      string,
      Record<
        string,
        {
          market: string;
          member_count: number;
          total_market_cap: number;
          weighted_pe: number | null;
          pe_sample_count: number;
        }
      >
    >;
  }>(`${API_PREFIX}/dojo-sphere/sectors/metrics?${query}`);
  const scopes = {} as SectorScopeMetricsResponse['scopes'];
  for (const [level, markets] of Object.entries(raw.scopes ?? {})) {
    const levelKey = level as SectorLevelKey;
    scopes[levelKey] = {};
    for (const [market, stats] of Object.entries(markets)) {
      const uiMarket = (market === 'sh' ? 'cn' : market) as MarketCode;
      scopes[levelKey]![uiMarket] = {
        market: uiMarket,
        member_count: stats.member_count,
        total_market_cap: stats.total_market_cap,
        weighted_pe: stats.weighted_pe,
        pe_sample_count: stats.pe_sample_count,
      };
    }
  }
  return {
    level1_id: raw.level1_id,
    level2_id: raw.level2_id,
    level3_id: raw.level3_id,
    scopes,
  };
}

export async function fetchSectorScopeMetrics(params: {
  level1Id: string;
  level2Id: string;
  level3Id: string;
}): Promise<SectorScopeMetricsResponse> {
  const bundle = await fetchSectorAnalysisBundle(params);
  return bundle.metrics;
}

export async function fetchSectorConstituents(params: {
  level1Id: string;
  level2Id: string;
  level3Id: string;
  market: MarketCode;
  scope: SectorLevelKey;
  /** Lookback window in trading days; when > 1, API fills window_change_percent. */
  days?: number;
}): Promise<SectorConstituentsResponse> {
  const query = new URLSearchParams({
    level1_id: params.level1Id,
    level2_id: params.level2Id,
    level3_id: params.level3Id,
    market: params.market,
    scope: params.scope,
  });
  if (params.days != null && params.days > 1) {
    query.set('days', String(params.days));
  }
  const raw = await fetchJson<{
    level1_id: string;
    level2_id: string;
    level3_id: string;
    scope: string;
    market?: string | null;
    items: SectorConstituentsResponse['items'];
  }>(`${API_PREFIX}/sector/constituents?${query}`);
  return mapSectorConstituents(raw);
}

export async function fetchSectorScopePerformance(params: {
  level1Id: string;
  level2Id: string;
  level3Id: string;
  scope: SectorLevelKey;
}): Promise<SectorPerformanceResponse> {
  const bundle = await fetchSectorAnalysisBundle({
    level1Id: params.level1Id,
    level2Id: params.level2Id,
    level3Id: params.level3Id,
  });
  const performance = bundle.performanceByLevel[params.scope];
  if (!performance) {
    const raw = await fetchSectorAnalysisRaw(params);
    return mapSectorPerformance(raw, params.scope);
  }
  return performance;
}
