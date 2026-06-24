import type {
  BenchmarkCard,
  BenchmarkKlinePoint,
  BilingualText,
  MarketCode,
  SectorItem,
  SectorMemberItem,
} from '../../types/dojoMesh';
import type {
  SectorPerformancePoint,
  SectorPerformanceResponse,
  SectorScopeMetricsResponse,
  SectorConstituentsResponse,
  SectorLevelKey,
} from '../../types/dojoSphere';
import type {
  SectorTaxonomyDocument,
  SectorTaxonomyL1,
  SectorTaxonomyL2,
  SectorTaxonomyL3,
} from '../../types/sectorTaxonomy';
import { sectorLinkKey, withStrength } from '../../utils/sectorLink';
import { DATA_START_DATE } from '../../utils/klineDate';

type Bilingual = { zh: string; en: string };

export interface AlphaTaxonomyTree {
  version: string;
  id_scheme: string;
  tree: Array<{
    level1_id: string;
    name: Bilingual;
    description?: Bilingual;
    children: Array<{
      level2_id: string;
      name: Bilingual;
      description?: Bilingual;
      children: Array<{
        level3_id: string;
        name: Bilingual;
        definition?: Bilingual;
      }>;
    }>;
  }>;
}

export interface AlphaSectorMoverItem {
  level1_id: string;
  level2_id: string;
  level3_id: string;
  concept_code: string;
  name: BilingualText;
  change_percent: number;
  avg_market_cap: number;
  member_count: number;
  sample_tickers: string[];
  top_members: Array<{
    ticker: string;
    name: BilingualText;
    last_price: number;
    market_cap: number;
    change_percent: number;
  }>;
}

export interface AlphaSectorAnalysis {
  level1_id: string;
  level2_id: string;
  level3_id: string;
  scope: string;
  metrics_by_scope: Record<string, Record<string, {
    market: string;
    member_count: number;
    total_market_cap: number;
    weighted_pe: number | null;
    pe_sample_count: number;
  }>>;
  performance_window_start?: string | null;
  performance_window_end?: string | null;
  performance_by_market: Record<string, Array<{ date: string; value: number }>>;
  stats_by_market: Record<string, {
    cumulative_return_pct?: number | null;
    sharpe_ratio?: number | null;
    max_drawdown_pct?: number | null;
    calmar_ratio?: number | null;
    volatility_pct?: number | null;
    trading_days: number;
  }>;
  members_by_market: Record<string, number>;
  performance_by_scope?: Record<
    string,
    {
      performance_window_start?: string | null;
      performance_window_end?: string | null;
      performance_by_market: Record<string, Array<{ date: string; value: number }>>;
      stats_by_market: AlphaSectorAnalysis['stats_by_market'];
      members_by_market: Record<string, number>;
    }
  >;
}

export function transformTaxonomy(raw: AlphaTaxonomyTree): SectorTaxonomyDocument {
  const level_1: SectorTaxonomyL1[] = raw.tree.map((l1) => ({
    id: l1.level1_id,
    name: l1.name,
    description: l1.description,
    level_2: l1.children.map((l2) => ({
      id: l2.level2_id,
      name: l2.name,
      description: l2.description,
      level_3: l2.children.map((l3) => ({
        id: l3.level3_id,
        name: l3.name,
        definition: l3.definition,
      })) as SectorTaxonomyL3[],
    })) as SectorTaxonomyL2[],
  }));
  return { version: raw.version, id_scheme: raw.id_scheme, level_1 };
}

export function mapConstituentToMember(
  item: {
    ticker: string;
    name: BilingualText;
    last_price?: number | null;
    market_cap?: number | null;
    change_percent?: number | null;
    window_change_percent?: number | null;
  },
  options?: { lookbackDays?: number },
): SectorMemberItem {
  const lookbackDays = options?.lookbackDays ?? 1;
  const daily = item.change_percent ?? 0;
  const windowChange = item.window_change_percent;
  const change =
    lookbackDays > 1 && windowChange != null ? windowChange : daily;
  return {
    ticker: item.ticker,
    name: item.name,
    last_price: item.last_price ?? undefined,
    market_cap: item.market_cap ?? undefined,
    change_percent: change,
  };
}

export function mapSectorMoverItem(item: AlphaSectorMoverItem, peers: AlphaSectorMoverItem[]): SectorItem {
  const members: SectorMemberItem[] = (item.top_members ?? []).map((member) => ({
    ticker: member.ticker,
    name: member.name,
    last_price: member.last_price,
    market_cap: member.market_cap,
    change_percent: member.change_percent ?? 0,
  }));
  const changePercent = item.change_percent ?? 0;
  const base: SectorItem = {
    concept_code: item.concept_code,
    name: item.name,
    change_percent: changePercent,
    avg_market_cap: item.avg_market_cap,
    level1_id: item.level1_id,
    level2_id: item.level2_id,
    level3_id: item.level3_id,
    strength: 0,
    sample_tickers: item.sample_tickers ?? [],
    member_count: item.member_count,
    members,
  };
  const peerItems = peers.map((peer) => ({
    concept_code: peer.concept_code,
    name: peer.name,
    change_percent: peer.change_percent ?? 0,
    avg_market_cap: peer.avg_market_cap,
    strength: 0,
    sample_tickers: peer.sample_tickers ?? [],
    member_count: peer.member_count,
    members: [],
  }));
  return withStrength(base, peerItems.length ? peerItems : [base]);
}

export function syntheticBenchmarkKline(price: number, changePercent: number): BenchmarkKlinePoint[] {
  const start = price / (1 + changePercent / 100);
  const end = price;
  return [
    { datetime: 'window-start', close: start },
    { datetime: 'window-end', close: end },
  ];
}

export function mapBenchmarkCards(
  market: MarketCode,
  snapshots: Array<{
    market: string;
    symbol: string;
    name: BilingualText;
    price: number;
    change_percent: number;
    kline?: BenchmarkKlinePoint[];
  }>,
): BenchmarkCard[] {
  return snapshots.map((row) => {
    const kline =
      row.kline && row.kline.length >= 2
        ? row.kline.map((point) => ({
            datetime: point.datetime,
            close: point.close,
          }))
        : syntheticBenchmarkKline(row.price, row.change_percent);
    return {
      market,
      symbol: row.symbol,
      name: row.name,
      price: row.price,
      change_percent: row.change_percent,
      kline,
    };
  });
}

export function mapSectorMetrics(raw: AlphaSectorAnalysis): SectorScopeMetricsResponse {
  return {
    level1_id: raw.level1_id,
    level2_id: raw.level2_id,
    level3_id: raw.level3_id,
    scopes: raw.metrics_by_scope as SectorScopeMetricsResponse['scopes'],
  };
}

/** Sector index return over `days` trading sessions (0 = cumulative since data start). */
export function windowReturnFromIndexSeries(
  points: Array<{ date: string; value: number }> | undefined,
  days: number,
): number | null {
  if (!points?.length) return null;
  if (days <= 0) {
    const start = points[0]?.value;
    const end = points[points.length - 1]?.value;
    if (start == null || end == null || start <= 0) return null;
    return Math.round(((end / start - 1) * 100) * 100) / 100;
  }
  const limit = days + 1;
  const tail = points.length >= limit ? points.slice(-limit) : points;
  if (tail.length < 2) return null;
  const start = tail[0]?.value;
  const end = tail[tail.length - 1]?.value;
  if (start == null || end == null || start <= 0) return null;
  return Math.round(((end / start - 1) * 100) * 100) / 100;
}

export function mergePerformancePoints(
  seriesByMarket: Record<string, Array<{ date: string; value: number }>>,
): SectorPerformancePoint[] {
  const dates = new Set<string>();
  for (const series of Object.values(seriesByMarket)) {
    for (const point of series) dates.add(point.date);
  }
  const sorted = Array.from(dates).sort();
  const indexByMarket: Partial<Record<MarketCode, Map<string, number>>> = {};
  for (const [market, series] of Object.entries(seriesByMarket)) {
    indexByMarket[market as MarketCode] = new Map(series.map((p) => [p.date, p.value]));
  }
  return sorted.map((date) => ({
    date,
    us: indexByMarket.us?.get(date) ?? null,
    cn: indexByMarket.cn?.get(date) ?? null,
    hk: indexByMarket.hk?.get(date) ?? null,
  }));
}

export function mapSectorPerformance(
  raw: AlphaSectorAnalysis,
  scope: SectorLevelKey,
): SectorPerformanceResponse {
  const scoped = raw.performance_by_scope?.[scope];
  const performance_by_market = scoped?.performance_by_market ?? raw.performance_by_market;
  const stats_by_market = scoped?.stats_by_market ?? raw.stats_by_market;
  const members_by_market = scoped?.members_by_market ?? raw.members_by_market;
  const window_end = scoped?.performance_window_end ?? raw.performance_window_end ?? null;

  const series_by_market = Object.fromEntries(
    Object.entries(performance_by_market).map(([market, points]) => [
      market,
      points.filter((point) => point.date >= DATA_START_DATE),
    ]),
  ) as SectorPerformanceResponse['series_by_market'];
  return {
    level1_id: raw.level1_id,
    level2_id: raw.level2_id,
    level3_id: raw.level3_id,
    scope,
    window_start: DATA_START_DATE,
    window_end,
    points: mergePerformancePoints(series_by_market),
    series_by_market,
    stats_by_market: stats_by_market as SectorPerformanceResponse['stats_by_market'],
    members_by_market: members_by_market as SectorPerformanceResponse['members_by_market'],
  };
}

export function mapSectorPerformanceByScope(
  raw: AlphaSectorAnalysis,
): Partial<Record<SectorLevelKey, SectorPerformanceResponse>> {
  const scopes = raw.performance_by_scope;
  if (scopes && Object.keys(scopes).length > 0) {
    return Object.fromEntries(
      (['L1', 'L2', 'L3'] as SectorLevelKey[]).map((scope) => [
        scope,
        mapSectorPerformance(raw, scope),
      ]),
    );
  }
  const scope = (raw.scope as SectorLevelKey) || 'L3';
  return { [scope]: mapSectorPerformance(raw, scope) };
}

export function mapSectorConstituents(raw: {
  level1_id: string;
  level2_id: string;
  level3_id: string;
  scope: string;
  market?: string | null;
  items: SectorConstituentsResponse['items'];
}): SectorConstituentsResponse {
  return {
    level1_id: raw.level1_id,
    level2_id: raw.level2_id,
    level3_id: raw.level3_id,
    scope: raw.scope as SectorLevelKey,
    market: (raw.market as MarketCode | null) ?? null,
    items: raw.items.map((item) => ({
      ...item,
      window_change_percent: item.window_change_percent ?? null,
    })),
  };
}

export function sectorItemFromAnalysis(
  market: MarketCode,
  linkKey: string,
  name: BilingualText,
  changePercent: number,
  memberCount: number,
  options?: {
    level1Id?: string;
    level2Id?: string;
    level3Id?: string;
    members?: SectorMemberItem[];
    sampleTickers?: string[];
  },
): SectorItem {
  const members = options?.members ?? [];
  return {
    concept_code: `${market.toUpperCase()}.L3.${linkKey}`,
    name,
    change_percent: changePercent,
    avg_market_cap: 0,
    level1_id: options?.level1Id,
    level2_id: options?.level2Id,
    level3_id: options?.level3Id,
    strength: 0,
    sample_tickers: options?.sampleTickers ?? members.slice(0, 3).map((m) => m.ticker),
    member_count: memberCount,
    members,
  };
}

function findRawMoverByLinkKey(
  movers: { gainers: AlphaSectorMoverItem[]; losers: AlphaSectorMoverItem[] },
  linkKey: string,
): AlphaSectorMoverItem | null {
  const needle = linkKey.trim().toLowerCase();
  for (const item of [...movers.gainers, ...movers.losers]) {
    const key = item.concept_code.match(/\.L3\.(.+)$/i)?.[1]?.toLowerCase();
    if (key === needle) return item;
  }
  return null;
}

export function findRawMoverAcrossMarkets(
  markets: Partial<
    Record<MarketCode, { gainers: AlphaSectorMoverItem[]; losers: AlphaSectorMoverItem[] }>
  >,
  linkKey: string,
): AlphaSectorMoverItem | null {
  for (const code of ['us', 'cn', 'hk'] as MarketCode[]) {
    const payload = markets[code];
    if (!payload) continue;
    const hit = findRawMoverByLinkKey(payload, linkKey);
    if (hit) return hit;
  }
  return null;
}

export function findMoverByLinkKey(
  movers: { gainers: AlphaSectorMoverItem[]; losers: AlphaSectorMoverItem[] },
  linkKey: string,
): SectorItem | null {
  const all = [...movers.gainers, ...movers.losers];
  const hit = all.find((item) => sectorLinkKey(item.concept_code) === linkKey);
  if (!hit) return null;
  return mapSectorMoverItem(hit, all);
}
