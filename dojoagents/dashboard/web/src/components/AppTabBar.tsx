import { useEffect, useRef, useState } from 'react';
import { APP_TAB_LABELS, type AppTab } from '../navigation/appTab';
import './AppTabBar.css';

interface AppTabBarProps {
  active: AppTab;
  onChange: (tab: AppTab) => void;
}

const DASHBOARD_TABS: AppTab[] = ['mesh', 'sphere', 'core'];
const PORTFOLIO_TABS: AppTab[] = ['folio'];
const ALL_TABS: AppTab[] = [...DASHBOARD_TABS, ...PORTFOLIO_TABS];

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

  const renderTab = (tab: AppTab) => (
    <button
      key={tab}
      type="button"
      role="tab"
      aria-selected={active === tab}
      className={`app-tab-bar__tab ${active === tab ? 'app-tab-bar__tab--active' : ''}`}
      onClick={() => selectTab(tab)}
    >
      {APP_TAB_LABELS[tab]}
    </button>
  );

  return (
    <div className="app-tab-bar-wrap" ref={rootRef}>
      <nav className="app-tab-bar" aria-label="Dojo 视图">
        <div className="app-tab-bar__group" role="presentation">
          {DASHBOARD_TABS.map(renderTab)}
        </div>
        <span className="app-tab-bar__divider" aria-hidden />
        <div className="app-tab-bar__group" role="presentation">
          {PORTFOLIO_TABS.map(renderTab)}
        </div>
      </nav>
      <div className="app-tab-popover">
        <button
          type="button"
          className={`app-tab-popover__trigger ${open ? 'app-tab-popover__trigger--open' : ''}`}
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-label="Dojo 视图"
          onClick={() => setOpen((prev) => !prev)}
        >
          <span className="app-tab-popover__value">{APP_TAB_LABELS[active]}</span>
          <ChevronIcon />
        </button>
        {open ? (
          <div className="app-tab-popover__menu" role="listbox" aria-label="Dojo 视图">
            {ALL_TABS.map((tab) => (
              <button
                key={tab}
                type="button"
                role="option"
                aria-selected={active === tab}
                className={`app-tab-popover__option ${active === tab ? 'app-tab-popover__option--active' : ''}`}
                onClick={() => selectTab(tab)}
              >
                {APP_TAB_LABELS[tab]}
              </button>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}
