import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type RefObject,
} from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import {
  MAX_SECTOR_DAYS,
  MAX_SECTOR_LIMIT,
  MIN_SECTOR_DAYS,
  MIN_SECTOR_LIMIT,
  SECTOR_DAY_PRESETS,
  clampSectorDays,
  clampSectorLimit,
  minCapDisplayFromYi,
  minCapYiFromDisplayInput,
} from '../../utils/marketSectorFilters';

interface MarketSectorMoversBarProps {
  days: number;
  minCapYi: number;
  sectorLimit: number;
  loading?: boolean;
  onDaysChange: (days: number) => void;
  onMinCapYiChange: (minCapYi: number) => void;
  onSectorLimitChange: (sectorLimit: number) => void;
}

function useClickOutside(ref: RefObject<HTMLElement | null>, onClose: () => void) {
  useEffect(() => {
    const handlePointerDown = (event: MouseEvent) => {
      if (!ref.current?.contains(event.target as Node)) onClose();
    };
    document.addEventListener('mousedown', handlePointerDown);
    return () => document.removeEventListener('mousedown', handlePointerDown);
  }, [onClose, ref]);
}

function commitOnEnter(event: KeyboardEvent<HTMLInputElement>) {
  if (event.key === 'Enter') event.currentTarget.blur();
}

export function MarketSectorMoversBar({
  days,
  minCapYi,
  sectorLimit,
  loading = false,
  onDaysChange,
  onMinCapYiChange,
  onSectorLimitChange,
}: MarketSectorMoversBarProps) {
  const { t, locale } = useTranslation();
  const [daysText, setDaysText] = useState(String(days));
  const [minCapText, setMinCapText] = useState(() => minCapDisplayFromYi(minCapYi, locale));
  const [limitText, setLimitText] = useState(String(sectorLimit));
  const [daysMenuOpen, setDaysMenuOpen] = useState(false);
  const daysWrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setDaysText(String(days));
  }, [days]);

  useEffect(() => {
    setMinCapText(minCapDisplayFromYi(minCapYi, locale));
  }, [minCapYi, locale]);

  useEffect(() => {
    setLimitText(String(sectorLimit));
  }, [sectorLimit]);

  const closeDaysMenu = useCallback(() => setDaysMenuOpen(false), []);
  useClickOutside(daysWrapRef, closeDaysMenu);

  const commitDays = useCallback(() => {
    const next = clampSectorDays(parseInt(daysText, 10));
    setDaysText(String(next));
    if (next !== days) onDaysChange(next);
  }, [days, daysText, onDaysChange]);

  const commitMinCap = useCallback(() => {
    const next = minCapYiFromDisplayInput(minCapText, locale);
    setMinCapText(minCapDisplayFromYi(next, locale));
    if (next !== minCapYi) onMinCapYiChange(next);
  }, [locale, minCapText, minCapYi, onMinCapYiChange]);

  const commitLimit = useCallback(() => {
    const next = clampSectorLimit(parseInt(limitText, 10));
    setLimitText(String(next));
    if (next !== sectorLimit) onSectorLimitChange(next);
  }, [limitText, sectorLimit, onSectorLimitChange]);

  const pickDaysPreset = (value: number) => {
    const next = clampSectorDays(value);
    setDaysText(String(next));
    onDaysChange(next);
    setDaysMenuOpen(false);
  };

  const daySuffix = locale === 'zh' ? '日' : 'D';
  const capSuffix = locale === 'zh' ? '亿' : 'B';

  const daysHint = t('marketPage.sectorDaysHintBody');
  const capHint = t('marketPage.sectorMinCapHintBody');
  const limitHint = t('marketPage.sectorLimitHintBody');

  return (
    <header className="mesh-sector-movers-bar" aria-label={t('marketPage.sectorMoversTitle')}>
      <h2 className="mesh-sector-movers-bar__title">{t('marketPage.sectorMoversTitle')}</h2>

      <div className="mesh-sector-movers-bar__filters" aria-busy={loading}>
        <div className="mesh-sector-movers-bar__item">
          <span className="mesh-sector-movers-bar__label" title={daysHint}>
            {t('marketPage.sectorDaysLabel')}
          </span>
          <div className="mesh-sector-movers-bar__control">
            <div
              ref={daysWrapRef}
              className={`mesh-sector-movers-bar__combo${daysMenuOpen ? ' is-open' : ''}`}
            >
              <input
                type="number"
                className="mesh-sector-movers-bar__input"
                min={MIN_SECTOR_DAYS}
                max={MAX_SECTOR_DAYS}
                step={1}
                inputMode="numeric"
                value={daysText}
                aria-label={daysHint}
                aria-expanded={daysMenuOpen}
                aria-haspopup="listbox"
                onChange={(event) => setDaysText(event.target.value)}
                onBlur={() => {
                  commitDays();
                  setDaysMenuOpen(false);
                }}
                onFocus={() => setDaysMenuOpen(true)}
                onClick={() => setDaysMenuOpen(true)}
                onKeyDown={commitOnEnter}
              />
              <button
                type="button"
                className="mesh-sector-movers-bar__combo-chevron"
                aria-label={t('marketPage.sectorDaysPreset')}
                tabIndex={-1}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => setDaysMenuOpen((open) => !open)}
              />
              {daysMenuOpen ? (
                <ul className="mesh-sector-movers-bar__menu" role="listbox">
                  {SECTOR_DAY_PRESETS.map((option) => (
                    <li key={option} role="presentation">
                      <button
                        type="button"
                        role="option"
                        aria-selected={days === option}
                        className={`mesh-sector-movers-bar__menu-item${
                          days === option ? ' is-active' : ''
                        }`}
                        onMouseDown={(event) => event.preventDefault()}
                        onClick={() => pickDaysPreset(option)}
                      >
                        {option}
                        {daySuffix}
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
            <span className="mesh-sector-movers-bar__suffix">{daySuffix}</span>
          </div>
        </div>

        <div className="mesh-sector-movers-bar__item">
          <span className="mesh-sector-movers-bar__label" title={capHint}>
            {t('marketPage.sectorMinCapLabel')}
          </span>
          <div className="mesh-sector-movers-bar__control">
            <input
              type="number"
              className="mesh-sector-movers-bar__input"
              min={0}
              step={locale === 'zh' ? 1 : 0.1}
              inputMode="decimal"
              placeholder={t('marketPage.sectorMinCapPlaceholder')}
              value={minCapText}
              aria-label={capHint}
              onChange={(event) => setMinCapText(event.target.value)}
              onBlur={commitMinCap}
              onKeyDown={commitOnEnter}
            />
            <span className="mesh-sector-movers-bar__suffix">{capSuffix}</span>
          </div>
        </div>

        <div className="mesh-sector-movers-bar__item">
          <span className="mesh-sector-movers-bar__label" title={limitHint}>
            {t('marketPage.sectorLimitLabel')}
          </span>
          <div className="mesh-sector-movers-bar__control">
            <input
              type="number"
              className="mesh-sector-movers-bar__input"
              min={MIN_SECTOR_LIMIT}
              max={MAX_SECTOR_LIMIT}
              step={1}
              inputMode="numeric"
              value={limitText}
              aria-label={limitHint}
              onChange={(event) => setLimitText(event.target.value)}
              onBlur={commitLimit}
              onKeyDown={commitOnEnter}
            />
          </div>
        </div>
      </div>
    </header>
  );
}
