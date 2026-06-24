import { fetchJson } from './http';
import {
  fetchMockBenchmarkCatalog,
  fetchMockDojoMeshOverview,
  USE_INTERACTIVE_MOCKS,
} from '../mocks/interactiveMockData';
import type {
  BenchmarkCard,
  DojoMeshOverview,
  DojoMeshOverviewQuery,
  MarketCode,
  MarketColumn,
  MarketStats,
  SectorItem,
} from '../types/dojoMesh';

const API_PREFIX = '/api/v1';
const MARKET_CODES: MarketCode[] = ['us', 'sh', 'hk'];

function normalizeMarketCode(market: string): MarketCode {
  return market === 'cn' ? 'sh' : (market as MarketCode);
}

interface OverviewMarketPayload {
  market: string;
  stats: MarketStats;
  default_benchmark?: string | null;
  benchmarks?: BenchmarkCard[];
}

interface MarketOverviewResponse {
  days: number;
  as_of?: string | null;
  markets: Partial<Record<string, OverviewMarketPayload>>;
}

interface LiveSectorsResponse {
  days: number;
  markets: Partial<
    Record<
      string,
      {
        gainers: SectorItem[];
        losers: SectorItem[];
      }
    >
  >;
}

export interface BenchmarkCatalogResponse {
  as_of?: string | null;
  markets: Partial<
    Record<
      MarketCode,
      {
        default_benchmark: string;
        benchmarks: BenchmarkCard[];
      }
    >
  >;
}

async function fetchMarketOverview(): Promise<MarketOverviewResponse | null> {
  try {
    return await fetchJson<MarketOverviewResponse>(`${API_PREFIX}/market/overview`);
  } catch {
    return null;
  }
}

async function fetchLiveMarketStats(): Promise<Partial<Record<MarketCode, MarketStats>> | null> {
  const overview = await fetchMarketOverview();
  if (!overview) return null;
  return Object.fromEntries(
    Object.entries(overview.markets ?? {})
      .filter((entry): entry is [string, OverviewMarketPayload] => Boolean(entry[1]))
      .map(([market, payload]) => [
        normalizeMarketCode(market),
        {
          ...payload.stats,
          market: normalizeMarketCode(payload.stats.market),
        },
      ]),
  ) as Partial<Record<MarketCode, MarketStats>>;
}

export async function fetchBenchmarkCatalog(): Promise<BenchmarkCatalogResponse> {
  if (USE_INTERACTIVE_MOCKS) return fetchMockBenchmarkCatalog();
  const overview = await fetchMarketOverview();
  return {
    as_of: overview?.as_of,
    markets: Object.fromEntries(
      Object.entries(overview?.markets ?? {})
        .filter((entry): entry is [string, OverviewMarketPayload] => Boolean(entry[1]))
        .map(([market, payload]) => [
          normalizeMarketCode(market),
          {
            default_benchmark: payload.default_benchmark ?? '',
            benchmarks: (payload.benchmarks ?? []).map((item) => ({
              ...item,
              market: normalizeMarketCode(item.market),
            })),
          },
        ]),
    ) as BenchmarkCatalogResponse['markets'],
  };
}

async function fetchLiveBenchmarks(): Promise<BenchmarkCatalogResponse | null> {
  try {
    return await fetchBenchmarkCatalog();
  } catch {
    return null;
  }
}

async function fetchLiveSectors(sectorLimit: number): Promise<LiveSectorsResponse | null> {
  try {
    const params = new URLSearchParams({ limit: String(sectorLimit) });
    const raw = await fetchJson<LiveSectorsResponse>(`${API_PREFIX}/market/sector-movers?${params}`);
    return {
      ...raw,
      markets: Object.fromEntries(
        Object.entries(raw.markets ?? {}).map(([market, payload]) => [
          normalizeMarketCode(market),
          payload,
        ]),
      ) as LiveSectorsResponse['markets'],
    };
  } catch {
    return null;
  }
}

function emptyMarketStats(market: MarketCode): MarketStats {
  return {
    market,
    listed_count: 0,
    total_market_cap: 0,
    weighted_pe: null,
    simple_pe: null,
    pe_sample_count: 0,
  };
}

function emptyMarketColumn(market: MarketCode): MarketColumn {
  return {
    stats: emptyMarketStats(market),
    benchmarks: [],
    gainers: [],
    losers: [],
  };
}

function buildMarketColumn(
  market: MarketCode,
  stats: Partial<Record<MarketCode, MarketStats>> | null,
  benchmarks: BenchmarkCatalogResponse | null,
  sectors: LiveSectorsResponse | null,
): MarketColumn {
  const column = emptyMarketColumn(market);

  if (stats?.[market]) {
    column.stats = stats[market];
  }

  const benchmarkPayload = benchmarks?.markets?.[market];
  if (benchmarkPayload?.benchmarks?.length) {
    const valid = benchmarkPayload.benchmarks.filter((b: BenchmarkCard) => b.kline?.length >= 2);
    if (valid.length) {
      column.benchmarks = valid;
      if (benchmarkPayload.default_benchmark) {
        column.default_benchmark = benchmarkPayload.default_benchmark;
      }
    }
  }

  const sectorPayload = sectors?.markets?.[market];
  if (sectorPayload) {
    column.gainers = sectorPayload.gainers ?? [];
    column.losers = sectorPayload.losers ?? [];
  }

  return column;
}

export const MARKET_COLUMNS: { code: MarketCode; flag: string; label: string }[] = [
  { code: 'us', flag: '🇺🇸', label: 'US' },
  { code: 'sh', flag: '🇨🇳', label: 'CN' },
  { code: 'hk', flag: '🇭🇰', label: 'HK' },
];

export async function fetchDojoMeshOverview(
  query: DojoMeshOverviewQuery = {},
): Promise<DojoMeshOverview> {
  if (USE_INTERACTIVE_MOCKS) return fetchMockDojoMeshOverview();
  const sectorLimit = query.sector_limit ?? 5;
  const [stats, benchmarks, sectors] = await Promise.all([
    fetchLiveMarketStats(),
    fetchLiveBenchmarks(),
    fetchLiveSectors(sectorLimit),
  ]);

  const markets = Object.fromEntries(
    MARKET_CODES.map((code) => [code, buildMarketColumn(code, stats, benchmarks, sectors)]),
  ) as Record<MarketCode, MarketColumn>;

  return {
    as_of: benchmarks?.as_of ?? new Date().toISOString().slice(0, 10),
    markets,
  };
}

interface CrossMarketSectorLookupResponse {
  link_key: string;
  markets: Partial<Record<MarketCode, SectorItem | null>>;
}

export async function fetchCrossMarketSectors(
  linkKey: string,
): Promise<Partial<Record<MarketCode, SectorItem | null>>> {
  if (USE_INTERACTIVE_MOCKS) {
    const overview = await fetchMockDojoMeshOverview();
    return Object.fromEntries(
      MARKET_CODES.map((code) => [
        code,
        overview.markets[code].gainers.find((sector) => sector.concept_code === linkKey) ??
          overview.markets[code].gainers[0] ??
          null,
      ]),
    ) as Partial<Record<MarketCode, SectorItem | null>>;
  }
  try {
    const params = new URLSearchParams({ link_key: linkKey });
    const res = await fetchJson<CrossMarketSectorLookupResponse>(
      `${API_PREFIX}/dojo-mesh/sectors/cross-market?${params}`,
    );
    return res.markets ?? {};
  } catch {
    return Object.fromEntries(MARKET_CODES.map((code) => [code, null])) as Partial<
      Record<MarketCode, SectorItem | null>
    >;
  }
}
