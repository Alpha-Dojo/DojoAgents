import { useEffect, useRef, useState } from 'react';
import { useTranslation } from '../hooks/useTranslation';
import type { AppLocale } from '../i18n/locale';
import './LanguageSwitcher.css';

const OPTIONS: AppLocale[] = ['zh', 'en'];

function GlobeIcon() {
  return (
    <svg
      className="lang-menu__icon"
      viewBox="0 0 24 24"
      width="14"
      height="14"
      aria-hidden
    >
      <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="1.5" />
      <path
        d="M3 12h18M12 3c2.8 3.2 2.8 14.8 0 18M12 3c-2.8 3.2-2.8 14.8 0 18"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

function ChevronIcon() {
  return (
    <svg
      className="lang-menu__chevron"
      viewBox="0 0 24 24"
      width="12"
      height="12"
      aria-hidden
    >
      <path
        d="M6 9l6 6 6-6"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function LanguageSwitcher() {
  const { locale, setLocale, t } = useTranslation();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;

    const handlePointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };

    window.addEventListener('mousedown', handlePointerDown);
    return () => window.removeEventListener('mousedown', handlePointerDown);
  }, [open]);

  const selectLocale = (code: AppLocale) => {
    setLocale(code);
    setOpen(false);
  };

  return (
    <div className="lang-menu" ref={rootRef}>
      <button
        type="button"
        className={`lang-menu__trigger ${open ? 'lang-menu__trigger--open' : ''}`}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={t('language.label')}
        onClick={() => setOpen((prev) => !prev)}
      >
        <GlobeIcon />
        <span className="lang-menu__value">{t(`language.${locale}`)}</span>
        <ChevronIcon />
      </button>
      {open && (
        <ul className="lang-menu__dropdown" role="listbox" aria-label={t('language.label')}>
          {OPTIONS.map((code) => (
            <li key={code} role="presentation">
              <button
                type="button"
                role="option"
                aria-selected={locale === code}
                className={`lang-menu__option ${locale === code ? 'lang-menu__option--active' : ''}`}
                onClick={() => selectLocale(code)}
              >
                {t(`language.${code}`)}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
