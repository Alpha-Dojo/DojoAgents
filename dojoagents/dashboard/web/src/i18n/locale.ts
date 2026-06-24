import type { BilingualText } from '../types/dojoMesh';

export type AppLocale = 'zh' | 'en';

const STORAGE_KEY = 'alphadojo-locale';

export function isAppLocale(value: unknown): value is AppLocale {
  return value === 'zh' || value === 'en';
}

export function readStoredLocale(): AppLocale {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return isAppLocale(raw) ? raw : 'zh';
  } catch {
    return 'zh';
  }
}

export function storeLocale(locale: AppLocale) {
  try {
    localStorage.setItem(STORAGE_KEY, locale);
  } catch {
    /* ignore */
  }
}

export function displayLocaleText(text: BilingualText, locale: AppLocale): string {
  if (locale === 'zh') return text.zh || text.en;
  return text.en || text.zh;
}

export function interpolate(
  template: string,
  vars: Record<string, string | number>,
): string {
  return template.replace(/\{(\w+)\}/g, (_, key: string) => String(vars[key] ?? ''));
}
