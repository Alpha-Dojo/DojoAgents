import { AppTabBar } from './AppTabBar';
import { LanguageSwitcher } from './LanguageSwitcher';
import { TradingClockSwitcher } from './TradingClockSwitcher';
import { useTranslation } from '../hooks/useTranslation';
import type { AppTab } from '../navigation/appTab';
import './AppTabBar.css';
import './Header.css';
import './LanguageSwitcher.css';
import './TradingClockSwitcher.css';

interface HeaderProps {
  activeTab: AppTab;
  onTabChange: (tab: AppTab) => void;
  agentOpen: boolean;
  onAgentToggle: () => void;
}

export function Header({
  activeTab,
  onTabChange,
  agentOpen,
  onAgentToggle,
}: HeaderProps) {
  const { t } = useTranslation();

  return (
    <header className="app-header">
      <div className="app-header__brand">
        <h1>Alpha Dojo</h1>
      </div>
      <div className="app-header__center">
        <AppTabBar active={activeTab} onChange={onTabChange} />
      </div>
      <div className="app-header__session">
        <div className="header-util">
          <TradingClockSwitcher />
          <span className="header-util__sep" aria-hidden />
          <LanguageSwitcher />
          <span className="header-util__sep" aria-hidden />
          <button
            type="button"
            className={`header-util__agent ${agentOpen ? 'header-util__agent--active' : ''}`}
            aria-expanded={agentOpen}
            aria-controls="dojo-agent-panel"
            aria-label={t('header.openAgent')}
            onClick={onAgentToggle}
          >
            <span className="header-util__agent-icon" aria-hidden>
              ✦
            </span>
            {t('header.agent')}
          </button>
        </div>
      </div>
    </header>
  );
}
