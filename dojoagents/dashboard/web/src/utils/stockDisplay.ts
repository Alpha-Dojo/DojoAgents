import type { BilingualText } from '../types/market';
import { displayLocaleText, type AppLocale } from '../i18n/locale';

/** Same zh/en priority as DojoCore header names. */
export function localizedStockName(
  names: { zh?: string; en?: string; fallback?: string },
  locale: AppLocale,
): string {
  const fallback = names.fallback?.trim() ?? '';
  return displayLocaleText(
    {
      zh: names.zh?.trim() || fallback,
      en: names.en?.trim() || fallback,
    } satisfies BilingualText,
    locale,
  );
}
