import { useTranslation } from '../hooks/useTranslation';
import type { AppLocale } from '../i18n/locale';
import { DropdownMenu } from './DropdownMenu';
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

  return (
    <DropdownMenu className="lang-menu">
      {({ close, open, toggle }) => (
        <>
          <button
            type="button"
            className={`lang-menu__trigger ${open ? 'lang-menu__trigger--open' : ''}`}
            aria-haspopup="listbox"
            aria-expanded={open}
            aria-label={t('language.label')}
            onClick={toggle}
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
                    onClick={() => {
                      setLocale(code);
                      close();
                    }}
                  >
                    {t(`language.${code}`)}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </DropdownMenu>
  );
}
