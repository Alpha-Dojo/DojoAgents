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

/** Sector L1/L2/L3 tree from backend SectorStore (query_sector_info cache). */
export async function fetchSectorTaxonomy(): Promise<SectorTaxonomyDocument> {
  if (USE_INTERACTIVE_MOCKS) return fetchMockSectorTaxonomy();
  return fetchJson<SectorTaxonomyDocument>(`${API_PREFIX}/sectors/taxonomy`);
}

export async function fetchSectorScopeMetrics(params: {
  level1Id: string;
  level2Id: string;
  level3Id: string;
}): Promise<SectorScopeMetricsResponse> {
  if (USE_INTERACTIVE_MOCKS) return fetchMockSectorScopeMetrics(params);
  const query = new URLSearchParams({
    level1_id: params.level1Id,
    level2_id: params.level2Id,
    level3_id: params.level3Id,
  });
  return fetchJson<SectorScopeMetricsResponse>(`${API_PREFIX}/dojo-sphere/sectors/metrics?${query}`);
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
    market: params.market,
    scope: params.scope,
  });
  return fetchJson<SectorConstituentsResponse>(`${API_PREFIX}/dojo-sphere/sectors/constituents?${query}`);
}

export async function fetchSectorScopePerformance(params: {
  level1Id: string;
  level2Id: string;
  level3Id: string;
  scope: SectorLevelKey;
}): Promise<SectorPerformanceResponse> {
  if (USE_INTERACTIVE_MOCKS) return fetchMockSectorScopePerformance(params);
  const query = new URLSearchParams({
    level1_id: params.level1Id,
    level2_id: params.level2Id,
    level3_id: params.level3Id,
    scope: params.scope,
  });
  return fetchJson<SectorPerformanceResponse>(`${API_PREFIX}/dojo-sphere/sectors/performance?${query}`);
}
