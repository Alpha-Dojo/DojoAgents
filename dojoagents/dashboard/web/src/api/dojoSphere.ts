import { fetchJson } from './http';
import {
  fetchMockSectorConstituents,
  fetchMockSectorScopeMetrics,
  fetchMockSectorScopePerformance,
  fetchMockSectorTaxonomy,
  USE_INTERACTIVE_MOCKS,
} from '../mocks/interactiveMockData';
import type { MarketCode } from '../types/dojoMesh';
import type {
  SectorConstituentsResponse,
  SectorLevelKey,
  SectorPerformanceResponse,
  SectorScopeMetricsResponse,
} from '../types/dojoSphere';
import type { SectorTaxonomyDocument } from '../types/sectorTaxonomy';

const API_PREFIX = '/api/v1';

function normalizeMarketCode<T extends string | null | undefined>(market: T): T | MarketCode {
  if (market === 'cn') return 'sh';
  return (market ?? null) as T | MarketCode;
}

interface SectorAnalysisApiResponse {
  level1_id: string;
  level2_id: string;
  level3_id: string;
  scope: SectorLevelKey;
  scopes: Partial<
    Record<
      SectorLevelKey,
      {
        scope: SectorLevelKey;
        metrics: SectorScopeMetricsResponse;
        performance: SectorPerformanceResponse;
      }
    >
  >;
}

export async function fetchSectorAnalysis(params: {
  level1Id: string;
  level2Id: string;
  level3Id: string;
  scope?: SectorLevelKey;
}): Promise<SectorAnalysisApiResponse> {
  const query = new URLSearchParams({
    level1_id: params.level1Id,
    level2_id: params.level2Id,
    level3_id: params.level3Id,
    scope: params.scope ?? 'L3',
  });
  return fetchJson<SectorAnalysisApiResponse>(`${API_PREFIX}/sector/analysis?${query}`);
}

export async function fetchSectorTaxonomy(): Promise<SectorTaxonomyDocument> {
  if (USE_INTERACTIVE_MOCKS) return fetchMockSectorTaxonomy();
  const raw = await fetchJson<{ taxonomy: SectorTaxonomyDocument }>(`${API_PREFIX}/utility/taxonomy/tree`);
  return raw.taxonomy;
}

export async function fetchSectorScopeMetrics(params: {
  level1Id: string;
  level2Id: string;
  level3Id: string;
}): Promise<SectorScopeMetricsResponse> {
  if (USE_INTERACTIVE_MOCKS) return fetchMockSectorScopeMetrics(params);
  const raw = await fetchSectorAnalysis(params);
  return raw.scopes.L3?.metrics ?? raw.scopes.L2?.metrics ?? raw.scopes.L1?.metrics ?? {
    level1_id: params.level1Id,
    level2_id: params.level2Id,
    level3_id: params.level3Id,
    scopes: { L1: {}, L2: {}, L3: {} },
  };
}

export async function fetchSectorConstituents(params: {
  level1Id: string;
  level2Id: string;
  level3Id: string;
  market: MarketCode;
  scope: SectorLevelKey;
}): Promise<SectorConstituentsResponse> {
  if (USE_INTERACTIVE_MOCKS) return fetchMockSectorConstituents(params);
  const query = new URLSearchParams({
    level1_id: params.level1Id,
    level2_id: params.level2Id,
    level3_id: params.level3Id,
    market: params.market === 'sh' ? 'cn' : params.market,
    scope: params.scope,
  });
  const raw = await fetchJson<SectorConstituentsResponse>(`${API_PREFIX}/sector/constituents?${query}`);
  return {
    ...raw,
    market: normalizeMarketCode(raw.market) as MarketCode | null,
    items: raw.items.map((item) => ({
      ...item,
      market: normalizeMarketCode(item.market) as MarketCode,
    })),
  };
}

export async function fetchSectorScopePerformance(params: {
  level1Id: string;
  level2Id: string;
  level3Id: string;
  scope: SectorLevelKey;
}): Promise<SectorPerformanceResponse> {
  if (USE_INTERACTIVE_MOCKS) return fetchMockSectorScopePerformance(params);
  const raw = await fetchSectorAnalysis(params);
  return raw.scopes[params.scope]?.performance ?? raw.scopes.L3?.performance ?? {
    level1_id: params.level1Id,
    level2_id: params.level2Id,
    level3_id: params.level3Id,
    scope: params.scope,
    window_start: null,
    window_end: null,
    points: [],
    series_by_market: {},
    stats_by_market: {},
    members_by_market: {},
  };
}
