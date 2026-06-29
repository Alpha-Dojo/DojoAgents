import type { MarketCode } from '../types/market';
import type { SectorPathSelection, SectorTaxonomyDocument } from '../types/sectorTaxonomy';
import { resolveSectorPathFromJump, selectionFromPath } from '../utils/sectorTaxonomy';

const STORAGE_KEY = 'alphadojo-sphere-sector';

export interface SectorJumpContext {
  concept_code: string;
  market: MarketCode;
  name_zh: string;
  name_en: string;
  link_key: string;
}

/** Survives React Strict Mode remounts within the same jump navigation. */
let pendingSectorJump: SectorJumpContext | null = null;
let pendingJumpSelection: SectorPathSelection | null = null;
let sectorViewBootstrapped = false;

export function saveSectorJumpContext(ctx: SectorJumpContext) {
  pendingSectorJump = ctx;
  pendingJumpSelection = null;
  sectorViewBootstrapped = false;
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(ctx));
  notifySectorNavigation();
}

export const SECTOR_NAVIGATE_EVENT = 'alphadojo-sphere-navigate';

export function notifySectorNavigation() {
  window.dispatchEvent(new CustomEvent(SECTOR_NAVIGATE_EVENT));
}

export function readSectorJumpContext(): SectorJumpContext | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as SectorJumpContext;
  } catch {
    return null;
  }
}

export function peekPendingSectorJumpContext(): SectorJumpContext | null {
  return pendingSectorJump ?? readSectorJumpContext();
}

export function clearPendingSectorJumpContext() {
  pendingSectorJump = null;
  sessionStorage.removeItem(STORAGE_KEY);
}

export function consumeSectorJumpContext(): SectorJumpContext | null {
  const ctx = peekPendingSectorJumpContext();
  if (ctx) clearPendingSectorJumpContext();
  return ctx;
}

export function clearSectorJumpContext() {
  clearPendingSectorJumpContext();
  pendingJumpSelection = null;
}

export function isSectorViewBootstrapped(): boolean {
  return sectorViewBootstrapped;
}

export function markSectorViewBootstrapped() {
  sectorViewBootstrapped = true;
}

export function resolveJumpSelection(
  taxonomy: SectorTaxonomyDocument,
): SectorPathSelection | null {
  if (pendingJumpSelection) return pendingJumpSelection;

  const jumpContext = peekPendingSectorJumpContext();
  if (!jumpContext) return null;

  const fromJump = resolveSectorPathFromJump(
    taxonomy,
    jumpContext.link_key,
    jumpContext.name_zh,
    jumpContext.name_en,
  );
  if (!fromJump) return null;

  pendingJumpSelection = selectionFromPath(fromJump);
  clearPendingSectorJumpContext();
  return pendingJumpSelection;
}
