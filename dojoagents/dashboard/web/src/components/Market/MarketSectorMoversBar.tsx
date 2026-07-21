import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type RefObject,
} from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import { EVENT_CATEGORIES } from '../../types/marketDynamics';
import { categoryLabelKey } from '../../utils/marketDynamicsFormat';
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
import { MarketDiscoveryDatePicker } from './MarketDiscoveryDatePicker';

export type MarketSectorTabId = 'discovery' | 'movers';

interface MarketSectorMoversBarProps {
  activeTab: MarketSectorTabId;
  onTabChange: (tab: MarketSectorTabId) => void;
  /** Distinguishes desktop/mobile instances that may both exist in the DOM. */
  idPrefix?: string;
  days: number;
  minCapYi: number;
  sectorLimit: number;
  eventCategory: string;
  discoveryDate: string;
  discoveryMinDate: string;
  discoveryMaxDate: string;
  loading?: boolean;
  onDaysChange: (days: number) => void;
  onMinCapYiChange: (minCapYi: number) => void;
  onSectorLimitChange: (sectorLimit: number) => void;
  onEventCategoryChange: (category: string) => void;
  onDiscoveryDateChange: (date: string) => void;
}

const SECTOR_TABS: { id: MarketSectorTabId; labelKey: string }[] = [
  { id: 'discovery', labelKey: 'marketPage.dailyDiscoveryTitle' },
  { id: 'movers', labelKey: 'marketPage.sectorMoversTitle' },
];

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
  activeTab,
  onTabChange,
  idPrefix = 'main',
  days,
  minCapYi,
  sectorLimit,
  eventCategory,
  discoveryDate,
  discoveryMinDate,
  discoveryMaxDate,
  loading = false,
  onDaysChange,
  onMinCapYiChange,
  onSectorLimitChange,
  onEventCategoryChange,
  onDiscoveryDateChange,
}: MarketSectorMoversBarProps) {
  const { t, locale } = useTranslation();
  const [daysText, setDaysText] = useState(String(days));
  const [minCapText, setMinCapText] = useState(() => minCapDisplayFromYi(minCapYi, locale));
  const [limitText, setLimitText] = useState(String(sectorLimit));
  const [daysMenuOpen, setDaysMenuOpen] = useState(false);
  const [eventCategoryMenuOpen, setEventCategoryMenuOpen] = useState(false);
  const daysWrapRef = useRef<HTMLDivElement>(null);
  const eventCategoryWrapRef = useRef<HTMLDivElement>(null);
  const showMoversOnlyFilters = activeTab === 'movers';
  const showDiscoveryFilters = activeTab === 'discovery';

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
  const closeEventCategoryMenu = useCallback(() => setEventCategoryMenuOpen(false), []);
  useClickOutside(daysWrapRef, closeDaysMenu);
  useClickOutside(eventCategoryWrapRef, closeEventCategoryMenu);

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
  const categoryHint = t('marketPage.eventCategoryHintBody');
  const timeHint = t('marketPage.eventTimeHintBody');

  return (
    <header className="mesh-sector-movers-bar" aria-label={t('marketPage.sectorPanelTabs')}>
      <div className="mesh-sector-movers-bar__tabs" role="tablist" aria-label={t('marketPage.sectorPanelTabs')}>
        {SECTOR_TABS.map((tab) => {
          const selected = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              id={`mesh-sector-tab-${tab.id}-${idPrefix}`}
              aria-selected={selected}
              aria-controls={`mesh-sector-panel-${tab.id}-${idPrefix}`}
              className={`mesh-sector-movers-bar__tab${selected ? ' mesh-sector-movers-bar__tab--active' : ''}`}
              onClick={() => onTabChange(tab.id)}
            >
              {t(tab.labelKey)}
            </button>
          );
        })}
      </div>

      <div className="mesh-sector-movers-bar__filters" aria-busy={loading}>
        {showDiscoveryFilters ? (
          <div className="mesh-sector-movers-bar__item">
            <span className="mesh-sector-movers-bar__label" title={timeHint}>
              {t('marketPage.eventTimeLabel')}
            </span>
            <div className="mesh-sector-movers-bar__control">
              <MarketDiscoveryDatePicker
                value={discoveryDate}
                minDate={discoveryMinDate}
                maxDate={discoveryMaxDate}
                disabled={loading && !discoveryDate}
                onChange={onDiscoveryDateChange}
              />
            </div>
          </div>
        ) : null}

        {showMoversOnlyFilters ? (
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
        ) : null}

        {showMoversOnlyFilters ? (
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
        ) : null}

        {showMoversOnlyFilters ? (
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
        ) : null}

        {showDiscoveryFilters ? (
          <div className="mesh-sector-movers-bar__item">
            <span className="mesh-sector-movers-bar__label" title={categoryHint}>
              {t('marketPage.eventCategoryLabel')}
            </span>
            <div className="mesh-sector-movers-bar__control">
              <div
                ref={eventCategoryWrapRef}
                className={`mesh-sector-movers-bar__combo mesh-sector-movers-bar__category-combo${
                  eventCategoryMenuOpen ? ' is-open' : ''
                }`}
              >
                <button
                  type="button"
                  className="mesh-sector-movers-bar__category-trigger"
                  aria-label={categoryHint}
                  aria-expanded={eventCategoryMenuOpen}
                  aria-haspopup="listbox"
                  onClick={() => setEventCategoryMenuOpen((open) => !open)}
                >
                  {eventCategory === 'all'
                    ? t('marketPage.eventCategoryAll')
                    : t(categoryLabelKey(eventCategory))}
                </button>
                <span className="mesh-sector-movers-bar__combo-chevron" aria-hidden="true" />
                {eventCategoryMenuOpen ? (
                  <ul className="mesh-sector-movers-bar__menu mesh-sector-movers-bar__menu--category" role="listbox">
                    {[
                      { value: 'all', label: t('marketPage.eventCategoryAll') },
                      ...EVENT_CATEGORIES.map((category) => ({
                        value: category,
                        label: t(categoryLabelKey(category)),
                      })),
                    ].map((option) => (
                      <li key={option.value} role="presentation">
                        <button
                          type="button"
                          role="option"
                          aria-selected={eventCategory === option.value}
                          className={`mesh-sector-movers-bar__menu-item${
                            eventCategory === option.value ? ' is-active' : ''
                          }`}
                          onMouseDown={(event) => event.preventDefault()}
                          onClick={() => {
                            onEventCategoryChange(option.value);
                            setEventCategoryMenuOpen(false);
                          }}
                        >
                          {option.label}
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </header>
  );
}
