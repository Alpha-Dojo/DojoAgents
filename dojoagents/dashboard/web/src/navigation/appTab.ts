export type AppTab = 'market' | 'sector' | 'entity' | 'folio';

const HISTORY_KEY = 'alphadojo-tab';

/** Legacy hash segments from pre-rename routes (mesh / sphere / core). */
const LEGACY_TAB_ALIASES: Record<string, AppTab> = {
  mesh: 'market',
  sphere: 'sector',
  core: 'entity',
};

export function isAppTab(value: unknown): value is AppTab {
  return value === 'market' || value === 'sector' || value === 'entity' || value === 'folio';
}

function normalizeTabSegment(segment: string): AppTab | null {
  if (isAppTab(segment)) {
    return segment;
  }
  return LEGACY_TAB_ALIASES[segment] ?? null;
}

export function parseTabHash(hash: string): AppTab | null {
  const match = hash.match(/^#\/([a-z]+)\/?/);
  if (!match) {
    return null;
  }
  return normalizeTabSegment(match[1]);
}

export function tabToHash(tab: AppTab): string {
  return tab === 'folio' ? '' : `#/${tab}`;
}

export function readTabFromHistory(): AppTab | null {
  const state = window.history.state;
  const stored = state?.[HISTORY_KEY];
  if (typeof stored === 'string') {
    return normalizeTabSegment(stored);
  }
  return null;
}

export function pushAppTab(tab: AppTab) {
  const hash = tabToHash(tab);
  window.history.pushState({ [HISTORY_KEY]: tab }, '', hash || window.location.pathname);
}

export function replaceAppTab(tab: AppTab) {
  const hash = tabToHash(tab);
  window.history.replaceState({ [HISTORY_KEY]: tab }, '', hash || window.location.pathname);
}

export function shouldRewriteLegacyHash(hash: string): boolean {
  return /^#\/(mesh|sphere|core)\/?/.test(hash);
}

export function resolveTabFromLocation(fallback: AppTab = 'folio'): AppTab {
  return readTabFromHistory() ?? parseTabHash(window.location.hash) ?? fallback;
}
