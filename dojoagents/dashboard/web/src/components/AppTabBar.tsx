import { APP_TAB_LABELS, type AppTab } from '../navigation/appTab';
import './AppTabBar.css';

interface AppTabBarProps {
  active: AppTab;
  onChange: (tab: AppTab) => void;
}

const DASHBOARD_TABS: AppTab[] = ['mesh', 'sphere', 'core'];
const PORTFOLIO_TABS: AppTab[] = ['folio'];

export function AppTabBar({ active, onChange }: AppTabBarProps) {
  const renderTab = (tab: AppTab) => (
    <button
      key={tab}
      type="button"
      role="tab"
      aria-selected={active === tab}
      className={`app-tab-bar__tab ${active === tab ? 'app-tab-bar__tab--active' : ''}`}
      onClick={() => onChange(tab)}
    >
      {APP_TAB_LABELS[tab]}
    </button>
  );

  return (
    <nav className="app-tab-bar" aria-label="Dojo 视图">
      <div className="app-tab-bar__group" role="presentation">
        {DASHBOARD_TABS.map(renderTab)}
      </div>
      <span className="app-tab-bar__divider" aria-hidden />
      <div className="app-tab-bar__group" role="presentation">
        {PORTFOLIO_TABS.map(renderTab)}
      </div>
    </nav>
  );
}
