const FOLIO_ACTIVE_ID_KEY = 'dojo-folio-active-id-v1';
const FOLIO_ACTIVE_NAME_KEY = 'dojo-folio-active-name-v1';

export const FOLIO_ACTIVE_CHANGED_EVENT = 'alphadojo-folio-active';

export function saveActiveFolioPortfolio(id: string, name?: string | null) {
  try {
    if (id) {
      sessionStorage.setItem(FOLIO_ACTIVE_ID_KEY, id);
    } else {
      sessionStorage.removeItem(FOLIO_ACTIVE_ID_KEY);
    }
    const trimmed = name?.trim();
    if (trimmed) {
      sessionStorage.setItem(FOLIO_ACTIVE_NAME_KEY, trimmed);
    }
  } catch {
    // ignore storage errors
  }
  window.dispatchEvent(new CustomEvent(FOLIO_ACTIVE_CHANGED_EVENT));
}

export function readActiveFolioPortfolioId(): string | null {
  try {
    const raw = sessionStorage.getItem(FOLIO_ACTIVE_ID_KEY);
    return raw?.trim() ? raw : null;
  } catch {
    return null;
  }
}

export function readActiveFolioPortfolioName(): string | null {
  try {
    const raw = sessionStorage.getItem(FOLIO_ACTIVE_NAME_KEY);
    return raw?.trim() ? raw : null;
  } catch {
    return null;
  }
}

export function resolveActiveFolioPortfolioName(locale: 'zh' | 'en'): string {
  return readActiveFolioPortfolioName() ?? (locale === 'zh' ? '当前组合' : 'this portfolio');
}
