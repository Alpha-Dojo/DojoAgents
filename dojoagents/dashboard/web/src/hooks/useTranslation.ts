import { displayLocaleText } from '../i18n/locale';
import { useLocaleContext } from '../i18n/LocaleContext';
import type { BilingualText } from '../types/market';

export function useTranslation() {
  const { locale, setLocale, t } = useLocaleContext();

  return {
    locale,
    setLocale,
    t,
    text: (value: BilingualText) => displayLocaleText(value, locale),
  };
}
