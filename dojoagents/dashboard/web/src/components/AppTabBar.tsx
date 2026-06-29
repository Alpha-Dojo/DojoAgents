import { useEffect, useRef, useState } from 'react';
import { useTranslation } from '../hooks/useTranslation';
import type { AppTab } from '../navigation/appTab';
import './AppTabBar.css';

interface AppTabBarProps {
  active: AppTab;
  onChange: (tab: AppTab) => void;
}

const PORTFOLIO_TABS: AppTab[] = ['folio'];
const DASHBOARD_TABS: AppTab[] = ['market', 'sector', 'entity'];
const ALL_TABS: AppTab[] = [...PORTFOLIO_TABS, ...DASHBOARD_TABS];

const TAB_LABEL_KEYS: Record<
  AppTab,
  'header.tabFolio' | 'header.tabMarket' | 'header.tabSector' | 'header.tabEntity'
> = {
  folio: 'header.tabFolio',
  market: 'header.tabMarket',
  sector: 'header.tabSector',
  entity: 'header.tabEntity',
};

function ChevronIcon() {
  return (
    <svg className="app-tab-bar__chevron" viewBox="0 0 24 24" width="12" height="12" aria-hidden>
      <path
        d="M6 9l6 6 6-6"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.75"
      />
    </svg>
  );
}

export function AppTabBar({ active, onChange }: AppTabBarProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;

    const handlePointerDown = (event: MouseEvent) => {
      if (rootRef.current?.contains(event.target as Node)) return;
      setOpen(false);
    };

    window.addEventListener('mousedown', handlePointerDown);
    return () => window.removeEventListener('mousedown', handlePointerDown);
  }, [open]);

  const selectTab = (tab: AppTab) => {
    onChange(tab);
    setOpen(false);
  };

  const tabLabel = (tab: AppTab) => t(TAB_LABEL_KEYS[tab]);

  const renderTab = (tab: AppTab) => (
    <button
      key={tab}
      type="button"
      role="tab"
      aria-selected={active === tab}
      className={`app-tab-bar__tab ${active === tab ? 'app-tab-bar__tab--active' : ''}`}
      onClick={() => selectTab(tab)}
    >
      {tabLabel(tab)}
    </button>
  );

  return (
    <div className="app-tab-bar-wrap" ref={rootRef}>
      <nav className="app-tab-bar" aria-label={t('header.tabNav')}>
        <div className="app-tab-bar__group" role="presentation">
          {PORTFOLIO_TABS.map(renderTab)}
        </div>
        <span className="app-tab-bar__divider" aria-hidden />
        <div className="app-tab-bar__group" role="presentation">
          {DASHBOARD_TABS.map(renderTab)}
        </div>
      </nav>
      <div className="app-tab-popover">
        <button
          type="button"
          className={`app-tab-popover__trigger ${open ? 'app-tab-popover__trigger--open' : ''}`}
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-label={t('header.tabNav')}
          onClick={() => setOpen((prev) => !prev)}
        >
          <span className="app-tab-popover__value">{tabLabel(active)}</span>
          <ChevronIcon />
        </button>
        {open ? (
          <div className="app-tab-popover__menu" role="listbox" aria-label={t('header.tabNav')}>
            {ALL_TABS.map((tab) => (
              <button
                key={tab}
                type="button"
                role="option"
                aria-selected={active === tab}
                className={`app-tab-popover__option ${active === tab ? 'app-tab-popover__option--active' : ''}`}
                onClick={() => selectTab(tab)}
              >
                {tabLabel(tab)}
              </button>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}
