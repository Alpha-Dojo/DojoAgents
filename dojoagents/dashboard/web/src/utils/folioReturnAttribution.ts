import type { FolioHolding, FolioPerformanceView } from '../types/dojoFolio';
import type { MarketCode } from '../types/dojoMesh';
import { resolveBenchmarkStats } from './folioPerformanceStats';

export type AttributionStepKey = 'benchmark' | 'sector' | 'stock' | 'trading' | 'total';

export interface AttributionWaterfallStep {
  key: AttributionStepKey;
  cumulativePct: number;
  deltaPct: number;
}

export interface AttributionContribution {
  label: string;
  kind: 'sector' | 'stock';
  tag: 'overweight' | 'underweight' | 'selection';
  contributionPct: number;
}

export interface FolioReturnAttribution {
  benchmarkLabel: string;
  benchmarkReturnPct: number;
  portfolioReturnPct: number;
  excessReturnPct: number;
  waterfall: AttributionWaterfallStep[];
  topPositive: AttributionContribution[];
  topNegative: AttributionContribution[];
  insightSector: string | null;
  insightWeakSector: string | null;
  primaryDriver: 'sector' | 'stock' | 'trading' | 'mixed' | null;
}

function holdingReturnPct(holding: FolioHolding): number {
  if (holding.cost <= 0) return 0;
  return ((holding.price / holding.cost - 1) * 100);
}

function primaryMarket(holdings: FolioHolding[]): MarketCode {
  const totals: Record<MarketCode, number> = { us: 0, cn: 0, hk: 0 };
  for (const row of holdings) totals[row.market] += row.marketValue;
  return (Object.entries(totals).sort((a, b) => b[1] - a[1])[0]?.[0] as MarketCode) ?? 'us';
}

function portfolioStatsReturn(
  performance: FolioPerformanceView | null | undefined,
  market: MarketCode,
): number | null {
  const pct = performance?.statsByMarket?.[market]?.cumulative_return_pct;
  return pct != null && !Number.isNaN(pct) ? pct : null;
}

export function computeReturnAttribution(
  holdings: FolioHolding[],
  performance: FolioPerformanceView | null | undefined,
  benchmarkSymbol: string | null,
  benchmarkLabel: string,
): FolioReturnAttribution | null {
  if (holdings.length === 0) return null;

  const market = primaryMarket(holdings);
  const benchmarkStats = resolveBenchmarkStats(performance, benchmarkSymbol);
  const benchmarkReturnPct = benchmarkStats?.cumulative_return_pct ?? 0;
  const portfolioReturnPct = portfolioStatsReturn(performance, market);
  if (portfolioReturnPct == null) return null;
  const excessReturnPct = portfolioReturnPct - benchmarkReturnPct;

  const totalMv = holdings.reduce((sum, row) => sum + row.marketValue, 0) || 1;
  const sectorGroups = new Map<
    string,
    { weight: number; returnPct: number; mv: number; count: number }
  >();

  for (const row of holdings) {
    const sector = row.sectorL1 || row.sector || row.name;
    const bucket = sectorGroups.get(sector) ?? { weight: 0, returnPct: 0, mv: 0, count: 0 };
    bucket.weight += row.weight;
    bucket.mv += row.marketValue;
    bucket.returnPct += holdingReturnPct(row) * row.marketValue;
    bucket.count += 1;
    sectorGroups.set(sector, bucket);
  }

  const sectors = [...sectorGroups.entries()].map(([label, bucket]) => ({
    label,
    weight: bucket.weight,
    returnPct: bucket.mv > 0 ? bucket.returnPct / bucket.mv : 0,
  }));
  const neutralWeight = sectors.length > 0 ? 100 / sectors.length : 0;

  let sectorAllocationPct = 0;
  for (const sector of sectors) {
    sectorAllocationPct += ((sector.weight - neutralWeight) / 100) * sector.returnPct;
  }

  let stockSelectionPct = 0;
  const stockContributions: AttributionContribution[] = [];
  for (const row of holdings) {
    const sector = row.sectorL1 || row.sector || row.name;
    const sectorRow = sectors.find((item) => item.label === sector);
    const sectorReturn = sectorRow?.returnPct ?? 0;
    const weight = row.marketValue / totalMv;
    const ret = holdingReturnPct(row);
    const contrib = weight * (ret - sectorReturn);
    stockSelectionPct += contrib;
    if (Math.abs(contrib) >= 0.01) {
      stockContributions.push({
        label: row.name || row.ticker,
        kind: 'stock',
        tag: 'selection',
        contributionPct: contrib,
      });
    }
  }

  const sectorContributions: AttributionContribution[] = sectors
    .map((sector) => ({
      label: sector.label,
      kind: 'sector' as const,
      tag: (sector.weight > neutralWeight ? 'overweight' : 'underweight') as
        | 'overweight'
        | 'underweight',
      contributionPct: ((sector.weight - neutralWeight) / 100) * sector.returnPct,
    }))
    .filter((item) => Math.abs(item.contributionPct) >= 0.01);

  let tradingPct = excessReturnPct - sectorAllocationPct - stockSelectionPct;
  if (!Number.isFinite(tradingPct)) tradingPct = 0;

  const waterfall: AttributionWaterfallStep[] = [
    { key: 'benchmark', cumulativePct: benchmarkReturnPct, deltaPct: benchmarkReturnPct },
    {
      key: 'sector',
      cumulativePct: benchmarkReturnPct + sectorAllocationPct,
      deltaPct: sectorAllocationPct,
    },
    {
      key: 'stock',
      cumulativePct: benchmarkReturnPct + sectorAllocationPct + stockSelectionPct,
      deltaPct: stockSelectionPct,
    },
    {
      key: 'trading',
      cumulativePct: portfolioReturnPct,
      deltaPct: tradingPct,
    },
    { key: 'total', cumulativePct: portfolioReturnPct, deltaPct: portfolioReturnPct },
  ];

  const ranked = [...sectorContributions, ...stockContributions].sort(
    (a, b) => b.contributionPct - a.contributionPct,
  );
  const topPositive = ranked.filter((item) => item.contributionPct > 0).slice(0, 3);
  const topNegative = ranked
    .filter((item) => item.contributionPct < 0)
    .sort((a, b) => a.contributionPct - b.contributionPct)
    .slice(0, 3);

  const drivers = [
    { key: 'sector' as const, abs: Math.abs(sectorAllocationPct) },
    { key: 'stock' as const, abs: Math.abs(stockSelectionPct) },
    { key: 'trading' as const, abs: Math.abs(tradingPct) },
  ].sort((a, b) => b.abs - a.abs);
  const primaryDriver =
    drivers[0].abs < 0.05 ? null : drivers[0].key === drivers[1].key ? drivers[0].key : drivers[0].abs > drivers[1].abs * 1.5 ? drivers[0].key : 'mixed';

  return {
    benchmarkLabel,
    benchmarkReturnPct,
    portfolioReturnPct,
    excessReturnPct,
    waterfall,
    topPositive,
    topNegative,
    insightSector: topPositive.find((item) => item.kind === 'sector')?.label ?? null,
    insightWeakSector: topNegative.find((item) => item.kind === 'sector')?.label ?? null,
    primaryDriver,
  };
}
