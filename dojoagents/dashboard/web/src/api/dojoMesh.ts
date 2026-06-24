import { fetchJson } from './http';
import {
  type AlphaSectorAnalysis,
  type AlphaSectorMoverItem,
  findMoverByLinkKey,
  findRawMoverAcrossMarkets,
  mapBenchmarkCards,
  mapConstituentToMember,
  mapSectorMoverItem,
  sectorItemFromAnalysis,
  windowReturnFromIndexSeries,
} from './adapters/transforms';
import type {
  BenchmarkCard,
  DojoMeshOverview,
  DojoMeshOverviewQuery,
  MarketCode,
  MarketColumn,
  MarketStats,
  SectorItem,
} from '../types/dojoMesh';
import { findSectorPathByLinkKey, selectionFromPath } from '../utils/sectorTaxonomy';
import { fetchSectorConstituents, fetchSectorTaxonomy } from './dojoSphere';

const API_PREFIX = '/api/v1';
const MARKET_CODES: MarketCode[] = ['us', 'cn', 'hk'];

interface MarketOverviewResponse {
  days: number;
  as_of?: string | null;
  window_start?: string | null;
  window_end?: string | null;
  markets: Partial<Record<MarketCode, MarketStats>>;
  benchmarks: Partial<
    Record<
      MarketCode,
      Array<{
        market: string;
        symbol: string;
        name: { zh: string; en: string };
        price: number;
        change_percent: number;
        window_start?: string | null;
        window_end?: string | null;
        kline?: Array<{ datetime: string; close: number }>;
      }>
    >
  >;
}

interface SectorMoversResponse {
  days: number;
  markets: Partial<
    Record<
      MarketCode,
      {
        gainers: AlphaSectorMoverItem[];
        losers: AlphaSectorMoverItem[];
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

async function fetchSectorMovers(options: {
  sectorLimit: number;
  days?: number;
  minCapByMarket?: Partial<Record<MarketCode, number>>;
}): Promise<SectorMoversResponse | null> {
  try {
    const params = new URLSearchParams({ limit: String(options.sectorLimit) });
    if (options.days != null) params.set('days', String(options.days));
    const caps = options.minCapByMarket ?? {};
    if (caps.us && caps.us > 0) params.set('min_cap_us', String(caps.us));
    if (caps.cn && caps.cn > 0) params.set('min_cap_cn', String(caps.cn));
    if (caps.hk && caps.hk > 0) params.set('min_cap_hk', String(caps.hk));
    return await fetchJson<SectorMoversResponse>(`${API_PREFIX}/market/sector-movers?${params}`);
  } catch {
    return null;
  }
}

export async function fetchBenchmarkCatalog(): Promise<BenchmarkCatalogResponse> {
  const overview = await fetchMarketOverview();
  const as_of = overview?.as_of ?? overview?.window_end ?? new Date().toISOString().slice(0, 10);
  const markets: BenchmarkCatalogResponse['markets'] = {};
  for (const code of MARKET_CODES) {
    const rows = overview?.benchmarks?.[code] ?? [];
    if (!rows.length) continue;
    const benchmarks = mapBenchmarkCards(code, rows);
    markets[code] = {
      default_benchmark: rows[0]?.symbol ?? '',
      benchmarks,
    };
  }
  return { as_of, markets };
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
  overview: MarketOverviewResponse | null,
  sectors: SectorMoversResponse | null,
): MarketColumn {
  const column = emptyMarketColumn(market);

  if (overview?.markets?.[market]) {
    column.stats = overview.markets[market]!;
  }

  const benchmarkRows = overview?.benchmarks?.[market] ?? [];
  if (benchmarkRows.length) {
    const benchmarks = mapBenchmarkCards(market, benchmarkRows);
    const valid = benchmarks.filter((b) => b.kline?.length >= 2);
    if (valid.length) {
      column.benchmarks = valid;
      column.default_benchmark = benchmarkRows[0]?.symbol;
    }
  }

  const sectorPayload = sectors?.markets?.[market];
  if (sectorPayload) {
    const peers = [...(sectorPayload.gainers ?? []), ...(sectorPayload.losers ?? [])];
    column.gainers = (sectorPayload.gainers ?? []).map((item) => mapSectorMoverItem(item, peers));
    column.losers = (sectorPayload.losers ?? []).map((item) => mapSectorMoverItem(item, peers));
  }

  return column;
}

export const MARKET_COLUMNS: { code: MarketCode; flag: string; label: string }[] = [
  { code: 'us', flag: '🇺🇸', label: 'US' },
  { code: 'cn', flag: '🇨🇳', label: 'CN' },
  { code: 'hk', flag: '🇭🇰', label: 'HK' },
];

export async function fetchDojoMeshOverview(
  query: DojoMeshOverviewQuery = {},
): Promise<DojoMeshOverview> {
  const sectorLimit = query.sector_limit ?? 5;
  const days = query.days ?? 1;
  const minCapByMarket = query.min_cap_by_market;
  const [overview, sectors] = await Promise.all([
    fetchMarketOverview(),
    fetchSectorMovers({ sectorLimit, days, minCapByMarket }),
  ]);

  const markets = Object.fromEntries(
    MARKET_CODES.map((code) => [code, buildMarketColumn(code, overview, sectors)]),
  ) as Record<MarketCode, MarketColumn>;

  return {
    as_of: overview?.as_of ?? overview?.window_end ?? new Date().toISOString().slice(0, 10),
    markets,
  };
}

async function fetchSectorAnalysisForPath(
  level1Id: string,
  level2Id: string,
  level3Id: string,
): Promise<AlphaSectorAnalysis | null> {
  try {
    const params = new URLSearchParams({
      level1_id: level1Id,
      level2_id: level2Id,
      level3_id: level3Id,
      scope: 'L3',
    });
    return await fetchJson<AlphaSectorAnalysis>(`${API_PREFIX}/sector/analysis?${params}`);
  } catch {
    return null;
  }
}

const CROSS_MARKET_MOVER_LIMIT = 20;

/** Resolve a level-3 sector in all markets, even when not in top gainers/losers. */
export async function fetchCrossMarketSectors(
  linkKey: string,
  options: { days?: number } = {},
): Promise<Partial<Record<MarketCode, SectorItem | null>>> {
  const empty = Object.fromEntries(MARKET_CODES.map((code) => [code, null])) as Partial<
    Record<MarketCode, SectorItem | null>
  >;

  try {
    const taxonomy = await fetchSectorTaxonomy();
    const path = findSectorPathByLinkKey(taxonomy, linkKey);
    if (!path) return empty;

    const taxonomyPath = selectionFromPath(path);
    const movers = await fetchSectorMovers({
      sectorLimit: CROSS_MARKET_MOVER_LIMIT,
      days: options.days ?? 1,
    });
    const pathMover = movers?.markets ? findRawMoverAcrossMarkets(movers.markets, linkKey) : null;
    const sectorPath = pathMover
      ? {
          level1Id: pathMover.level1_id,
          level2Id: pathMover.level2_id,
          level3Id: pathMover.level3_id,
        }
      : taxonomyPath;

    const analysis = await fetchSectorAnalysisForPath(
      sectorPath.level1Id,
      sectorPath.level2Id,
      sectorPath.level3Id,
    );

    const result: Partial<Record<MarketCode, SectorItem | null>> = {};
    for (const market of MARKET_CODES) {
      const marketMovers = movers?.markets?.[market] ?? { gainers: [], losers: [] };
      const fromMovers = movers ? findMoverByLinkKey(marketMovers, linkKey) : null;
      if (fromMovers) {
        result[market] = fromMovers;
        continue;
      }

      const stats = analysis?.stats_by_market?.[market];
      const memberCount = analysis?.members_by_market?.[market] ?? 0;
      if (!stats && memberCount <= 0) {
        result[market] = null;
        continue;
      }

      const lookbackDays = options.days ?? 1;
      const performancePoints = analysis?.performance_by_market?.[market];
      const windowChange =
        windowReturnFromIndexSeries(performancePoints, lookbackDays) ??
        (lookbackDays <= 0 ? stats?.cumulative_return_pct ?? null : null);

      let members: ReturnType<typeof mapConstituentToMember>[] = [];
      try {
        const constituents = await fetchSectorConstituents({
          level1Id: sectorPath.level1Id,
          level2Id: sectorPath.level2Id,
          level3Id: sectorPath.level3Id,
          market,
          scope: 'L3',
          days: options.days,
        });
        members = constituents.items.map((item) =>
          mapConstituentToMember(item, { lookbackDays: options.days ?? 1 }),
        );
      } catch {
        members = [];
      }

      result[market] = sectorItemFromAnalysis(
        market,
        linkKey,
        path.level3.name,
        windowChange ?? stats?.cumulative_return_pct ?? 0,
        members.length || memberCount,
        {
          level1Id: sectorPath.level1Id,
          level2Id: sectorPath.level2Id,
          level3Id: sectorPath.level3Id,
          members: members.slice(0, 20),
        },
      );
    }
    return result;
  } catch {
    return empty;
  }
}
