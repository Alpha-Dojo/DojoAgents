import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';
import { enMessages } from './messages/en';
import { zhMessages, type MessageTree } from './messages/zh';
import {
  interpolate,
  readStoredLocale,
  storeLocale,
  type AppLocale,
} from './locale';

interface LocaleContextValue {
  locale: AppLocale;
  setLocale: (locale: AppLocale) => void;
  t: TranslateFn;
}

type TranslateFn = (key: string, vars?: Record<string, string | number>) => string;

const LocaleContext = createContext<LocaleContextValue | null>(null);

const MESSAGES: Record<AppLocale, MessageTree> = {
  zh: zhMessages,
  en: enMessages,
};

function lookupMessage(messages: MessageTree, key: string): string | undefined {
  const parts = key.split('.');
  let node: unknown = messages;
  for (const part of parts) {
    if (node == null || typeof node !== 'object' || !(part in node)) return undefined;
    node = (node as Record<string, unknown>)[part];
  }
  return typeof node === 'string' ? node : undefined;
}

function createTranslate(locale: AppLocale): TranslateFn {
  return (key, vars) => {
    const template =
      lookupMessage(MESSAGES[locale], key) ?? lookupMessage(MESSAGES.zh, key) ?? key;
    return vars ? interpolate(template, vars) : template;
  };
}

export function LocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<AppLocale>(() => readStoredLocale());

  const setLocale = useCallback((next: AppLocale) => {
    setLocaleState(next);
    storeLocale(next);
  }, []);

  const value = useMemo(
    () => ({
      locale,
      setLocale,
      t: createTranslate(locale),
    }),
    [locale, setLocale],
  );

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useLocaleContext() {
  const ctx = useContext(LocaleContext);
  if (!ctx) {
    throw new Error('useLocaleContext must be used within LocaleProvider');
  }
  return ctx;
}
