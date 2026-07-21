import type { MarketCode } from '../types/market';

export const SECTOR_DAY_PRESETS = [1, 3, 5, 10, 22] as const;

export const MIN_SECTOR_DAYS = 1;
export const MAX_SECTOR_DAYS = 90;

export const MIN_SECTOR_LIMIT = 1;
export const MAX_SECTOR_LIMIT = 20;
export const DEFAULT_SECTOR_LIMIT = 5;

/** Default sector total-market-cap floor in 亿 (local currency). */
export const DEFAULT_MIN_CAP_YI = 200;

/** One 亿 = 1e8 in each market's local currency (CNY / USD / HKD). */
export const MIN_CAP_YI = 1e8;

/** 10 亿 = 1 billion (B) in EN display. */
export const YI_PER_BILLION = 10;

/** Bumped when default filter values change so stale localStorage is refreshed. */
const STORAGE_KEY = 'alphadojo-mesh-sector-filters:v2';

export interface MeshSectorFilterState {
  /** Lookback window in trading days (1–90). */
  days: number;
  /** Minimum sector total market cap in 亿 (local currency); 0 = no floor. */
  minCapYi: number;
  /** Top N gainers and losers per market (1–20). */
  sectorLimit: number;
}

export const DEFAULT_MESH_SECTOR_FILTERS: MeshSectorFilterState = {
  days: 1,
  minCapYi: DEFAULT_MIN_CAP_YI,
  sectorLimit: DEFAULT_SECTOR_LIMIT,
};

export function clampSectorDays(value: number): number {
  if (!Number.isFinite(value)) return DEFAULT_MESH_SECTOR_FILTERS.days;
  return Math.min(MAX_SECTOR_DAYS, Math.max(MIN_SECTOR_DAYS, Math.round(value)));
}

export function clampSectorLimit(value: number): number {
  if (!Number.isFinite(value)) return DEFAULT_SECTOR_LIMIT;
  return Math.min(MAX_SECTOR_LIMIT, Math.max(MIN_SECTOR_LIMIT, Math.round(value)));
}

export function normalizeMinCapYi(raw: string | number): number {
  const value = typeof raw === 'string' ? parseFloat(raw.trim()) : raw;
  if (!Number.isFinite(value) || value <= 0) return 0;
  return Math.round(value * 10) / 10;
}

function formatMinCapDisplayNumber(value: number): string {
  const rounded = Math.round(value * 10) / 10;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
}

/** Format stored 亿 value for the cap-floor input (ZH: 亿, EN: B). */
export function minCapDisplayFromYi(minCapYi: number, locale: string): string {
  if (minCapYi <= 0) return '';
  if (locale === 'zh') return formatMinCapDisplayNumber(minCapYi);
  return formatMinCapDisplayNumber(minCapYi / YI_PER_BILLION);
}

/** Parse cap-floor input back to stored 亿. */
export function minCapYiFromDisplayInput(raw: string, locale: string): number {
  const value = parseFloat(raw.trim());
  if (!Number.isFinite(value) || value <= 0) return 0;
  const yi = locale === 'zh' ? value : value * YI_PER_BILLION;
  return normalizeMinCapYi(yi);
}

export function minCapThresholdsFromYi(minCapYi: number): Record<MarketCode, number> {
  if (minCapYi <= 0) {
    return { us: 0, cn: 0, hk: 0 };
  }
  const abs = minCapYi * MIN_CAP_YI;
  return { us: abs, cn: abs, hk: abs };
}

export function minCapKeyFromFilters(filters: MeshSectorFilterState): string {
  const caps = minCapThresholdsFromYi(filters.minCapYi);
  return `us${caps.us}-cn${caps.cn}-hk${caps.hk}`;
}

function legacyPresetToYi(preset: string | undefined): number {
  switch (preset) {
    case 'low':
      return 10;
    case 'mid':
      return 50;
    case 'high':
      return 100;
    default:
      return 0;
  }
}

export function readMeshSectorFilters(): MeshSectorFilterState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_MESH_SECTOR_FILTERS;
    const parsed = JSON.parse(raw) as Partial<
      MeshSectorFilterState & {
        minCapPreset?: string;
        minCapByMarket?: Partial<Record<MarketCode, string>>;
      }
    >;

    const minCapYi =
      parsed.minCapYi != null
        ? normalizeMinCapYi(parsed.minCapYi)
        : legacyPresetToYi(
            parsed.minCapPreset ??
              parsed.minCapByMarket?.cn ??
              parsed.minCapByMarket?.us ??
              parsed.minCapByMarket?.hk,
          );

    return {
      days: clampSectorDays(parsed.days ?? DEFAULT_MESH_SECTOR_FILTERS.days),
      minCapYi,
      sectorLimit: clampSectorLimit(parsed.sectorLimit ?? DEFAULT_SECTOR_LIMIT),
    };
  } catch {
    return DEFAULT_MESH_SECTOR_FILTERS;
  }
}

export function storeMeshSectorFilters(state: MeshSectorFilterState): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}
