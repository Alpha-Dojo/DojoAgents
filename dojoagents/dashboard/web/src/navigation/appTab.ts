export type AppTab = 'mesh' | 'sphere' | 'core' | 'folio';

export const APP_TAB_LABELS: Record<AppTab, string> = {
  mesh: 'DojoMesh',
  sphere: 'DojoSphere',
  core: 'DojoCore',
  folio: 'DojoFolio',
};

const HISTORY_KEY = 'alphadojo-tab';

export function isAppTab(value: unknown): value is AppTab {
  return value === 'mesh' || value === 'sphere' || value === 'core' || value === 'folio';
}

export function parseTabHash(hash: string): AppTab | null {
  const match = hash.match(/^#\/(mesh|sphere|core|folio)\/?/);
  return match && isAppTab(match[1]) ? match[1] : null;
}

export function tabToHash(tab: AppTab): string {
  return tab === 'mesh' ? '' : `#/${tab}`;
}

export function readTabFromHistory(): AppTab | null {
  const state = window.history.state;
  if (state && isAppTab(state[HISTORY_KEY])) {
    return state[HISTORY_KEY];
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
