import type { FolioHolding, FolioPerformanceView } from '../types/dojoFolio';
import type { MarketCode } from '../types/dojoMesh';
import { FOLIO_MARKETS } from '../types/dojoFolio';
import { resolveBenchmarkStats } from './folioPerformanceStats';

export type RiskStatus = 'red' | 'yellow' | 'green';

export interface RiskExposureRow {
  id: string;
  status: RiskStatus;
  current: string;
  limit: string;
  noteKey: string;
  noteVars?: Record<string, string | number>;
}

export interface FolioRiskExposure {
  rows: RiskExposureRow[];
  topSector: string | null;
  topSectorWeight: number;
  maxHoldingLabel: string | null;
  maxHoldingWeight: number;
  dominantMarket: MarketCode | null;
  dominantMarketWeight: number;
}

const LIMITS = {
  sectorConcentration: 35,
  maxHolding: 15,
  usMarketMax: 80,
  liquidityDays: 3,
  betaMax: 1.5,
};

function marketWeights(holdings: FolioHolding[]): Record<MarketCode, number> {
  const totals: Record<MarketCode, number> = { us: 0, cn: 0, hk: 0 };
  let sum = 0;
  for (const row of holdings) {
    totals[row.market] += row.marketValue;
    sum += row.marketValue;
  }
  if (sum <= 0) return totals;
  return {
    us: (totals.us / sum) * 100,
    cn: (totals.cn / sum) * 100,
    hk: (totals.hk / sum) * 100,
  };
}

function sectorConcentration(holdings: FolioHolding[]): { sector: string; weight: number } {
  const map = new Map<string, number>();
  for (const row of holdings) {
    const key = row.sectorL1 || row.sector || row.name;
    map.set(key, (map.get(key) ?? 0) + row.weight);
  }
  let topSector = '';
  let topWeight = 0;
  for (const [sector, weight] of map) {
    if (weight > topWeight) {
      topSector = sector;
      topWeight = weight;
    }
  }
  return { sector: topSector, weight: topWeight };
}

function maxHolding(holdings: FolioHolding[]): { label: string; weight: number } {
  let label = '';
  let weight = 0;
  for (const row of holdings) {
    if (row.weight > weight) {
      weight = row.weight;
      label = row.name || row.ticker;
    }
  }
  return { label, weight };
}

function estimateLiquidityDays(holdings: FolioHolding[]): number {
  if (holdings.length === 0) return 0;
  const usHeavy = holdings.filter((row) => row.market === 'us').length / holdings.length;
  const cnHeavy = holdings.filter((row) => row.market === 'cn').length / holdings.length;
  if (cnHeavy > 0.5) return 2.4;
  if (usHeavy > 0.5) return 1.2;
  return 1.8;
}

function estimateBeta(
  performance: FolioPerformanceView | null | undefined,
  benchmarkSymbol: string | null,
): number {
  const benchmark = resolveBenchmarkStats(performance, benchmarkSymbol);
  let bestMarket: MarketCode = 'us';
  let bestVol = 0;
  for (const market of FOLIO_MARKETS) {
    const vol = performance?.statsByMarket?.[market]?.volatility_pct ?? 0;
    if (vol > bestVol) {
      bestVol = vol;
      bestMarket = market;
    }
  }
  const portVol = performance?.statsByMarket?.[bestMarket]?.volatility_pct ?? bestVol;
  const benchVol = benchmark?.volatility_pct ?? 0;
  if (portVol > 0 && benchVol > 0) return Number((portVol / benchVol).toFixed(2));
  return 1;
}

function statusForRatio(value: number, limit: number, invert = false): RiskStatus {
  const ratio = invert ? limit / Math.max(value, 0.001) : value / limit;
  if (ratio > 1) return 'red';
  if (ratio > 0.9) return 'yellow';
  return 'green';
}

export function computeRiskExposure(
  holdings: FolioHolding[],
  performance: FolioPerformanceView | null | undefined,
  benchmarkSymbol: string | null,
): FolioRiskExposure | null {
  if (holdings.length === 0) return null;

  const sector = sectorConcentration(holdings);
  const holding = maxHolding(holdings);
  const markets = marketWeights(holdings);
  const liquidity = estimateLiquidityDays(holdings);
  const beta = estimateBeta(performance, benchmarkSymbol);

  const dominantMarket = (Object.entries(markets).sort((a, b) => b[1] - a[1])[0]?.[0] ??
    'us') as MarketCode;
  const dominantWeight = markets[dominantMarket];

  const rows: RiskExposureRow[] = [
    {
      id: 'sector',
      status: statusForRatio(sector.weight, LIMITS.sectorConcentration),
      current: `${sector.weight.toFixed(1)}%`,
      limit: `${LIMITS.sectorConcentration.toFixed(1)}%`,
      noteKey: 'folio.riskNoteSector',
      noteVars: { sector: sector.sector },
    },
    {
      id: 'holding',
      status: statusForRatio(holding.weight, LIMITS.maxHolding),
      current: `${holding.weight.toFixed(1)}%`,
      limit: `${LIMITS.maxHolding.toFixed(1)}%`,
      noteKey: 'folio.riskNoteHolding',
    },
    {
      id: 'market',
      status: statusForRatio(dominantWeight, LIMITS.usMarketMax),
      current: `${dominantMarket.toUpperCase()} ${dominantWeight.toFixed(0)}%`,
      limit: `${dominantMarket.toUpperCase()} ${LIMITS.usMarketMax}%`,
      noteKey: 'folio.riskNoteMarket',
    },
    {
      id: 'liquidity',
      status: statusForRatio(liquidity, LIMITS.liquidityDays),
      current: `${liquidity.toFixed(1)}`,
      limit: `${LIMITS.liquidityDays.toFixed(1)}`,
      noteKey: 'folio.riskNoteLiquidity',
    },
    {
      id: 'beta',
      status: statusForRatio(beta, LIMITS.betaMax),
      current: beta.toFixed(2),
      limit: LIMITS.betaMax.toFixed(2),
      noteKey: 'folio.riskNoteBeta',
    },
  ];

  return {
    rows,
    topSector: sector.sector || null,
    topSectorWeight: sector.weight,
    maxHoldingLabel: holding.label || null,
    maxHoldingWeight: holding.weight,
    dominantMarket,
    dominantMarketWeight: dominantWeight,
  };
}
