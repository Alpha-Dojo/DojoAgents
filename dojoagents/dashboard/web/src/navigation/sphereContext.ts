import type { MarketCode } from '../types/dojoMesh';
import type { SectorPathSelection, SectorTaxonomyDocument } from '../types/sectorTaxonomy';
import { resolveSectorPathFromJump, selectionFromPath } from '../utils/sectorTaxonomy';

const STORAGE_KEY = 'alphadojo-sphere-sector';

export interface SphereSectorContext {
  concept_code: string;
  market: MarketCode;
  name_zh: string;
  name_en: string;
  link_key: string;
}

/** Survives React Strict Mode remounts within the same jump navigation. */
let pendingSphereJump: SphereSectorContext | null = null;
let pendingJumpSelection: SectorPathSelection | null = null;
let sphereViewBootstrapped = false;

export function saveSphereSectorContext(ctx: SphereSectorContext) {
  pendingSphereJump = ctx;
  pendingJumpSelection = null;
  sphereViewBootstrapped = false;
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(ctx));
  notifySphereNavigation();
}

export const SPHERE_NAVIGATE_EVENT = 'alphadojo-sphere-navigate';

export function notifySphereNavigation() {
  window.dispatchEvent(new CustomEvent(SPHERE_NAVIGATE_EVENT));
}

export function readSphereSectorContext(): SphereSectorContext | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as SphereSectorContext;
  } catch {
    return null;
  }
}

export function peekPendingSphereJumpContext(): SphereSectorContext | null {
  return pendingSphereJump ?? readSphereSectorContext();
}

export function clearPendingSphereJumpContext() {
  pendingSphereJump = null;
  sessionStorage.removeItem(STORAGE_KEY);
}

export function consumeSphereSectorContext(): SphereSectorContext | null {
  const ctx = peekPendingSphereJumpContext();
  if (ctx) clearPendingSphereJumpContext();
  return ctx;
}

export function clearSphereSectorContext() {
  clearPendingSphereJumpContext();
  pendingJumpSelection = null;
}

export function isSphereViewBootstrapped(): boolean {
  return sphereViewBootstrapped;
}

export function markSphereViewBootstrapped() {
  sphereViewBootstrapped = true;
}

export function resolveJumpSelection(
  taxonomy: SectorTaxonomyDocument,
): SectorPathSelection | null {
  if (pendingJumpSelection) return pendingJumpSelection;

  const jumpContext = peekPendingSphereJumpContext();
  if (!jumpContext) return null;

  const fromJump = resolveSectorPathFromJump(
    taxonomy,
    jumpContext.link_key,
    jumpContext.name_zh,
    jumpContext.name_en,
  );
  if (!fromJump) return null;

  pendingJumpSelection = selectionFromPath(fromJump);
  clearPendingSphereJumpContext();
  return pendingJumpSelection;
}
