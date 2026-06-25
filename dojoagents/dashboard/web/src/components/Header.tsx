import { AppTabBar } from './AppTabBar';
import { LanguageSwitcher } from './LanguageSwitcher';
import { TradingClockSwitcher } from './TradingClockSwitcher';
import { useTranslation } from '../hooks/useTranslation';
import type { AppTab } from '../navigation/appTab';
import './AppTabBar.css';
import './Header.css';
import './LanguageSwitcher.css';
import './TradingClockSwitcher.css';
import Logo from '../assets/images/logo.png';

interface HeaderProps {
  activeTab: AppTab;
  onTabChange: (tab: AppTab) => void;
  agentOpen: boolean;
  agentPinned?: boolean;
  onAgentToggle: () => void;
  settingsOpen: boolean;
  onSettingsOpen: () => void;
}

export function Header({
  activeTab,
  onTabChange,
  agentOpen,
  agentPinned = false,
  onAgentToggle,
  settingsOpen,
  onSettingsOpen,
}: HeaderProps) {
  const { t } = useTranslation();

  return (
    <header className="app-header">
      <div className="app-header__brand">
        <img src={Logo} alt="Alpha Dojo" className="app-header__logo" />
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
            className={`icon-button header-util__icon-button ${settingsOpen ? "header-util__icon-button--active icon-button--active" : ""}`}
            aria-expanded={settingsOpen}
            aria-label={t("header.openSettings")}
            title={t("header.settings")}
            onClick={onSettingsOpen}
          >
            <svg
              width="12"
              height="12"
              viewBox="0 0 12 12"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path
                d="M11.2103 7.5252L10.333 6.77515C10.3746 6.52068 10.396 6.26084 10.396 6.001C10.396 5.74117 10.3746 5.48133 10.333 5.22685L11.2103 4.47681C11.3456 4.36163 11.3952 4.17412 11.3349 4.00536L11.3228 3.97053C11.0804 3.29416 10.7215 2.67269 10.2554 2.12356L10.2313 2.09543C10.1161 1.96015 9.9299 1.90926 9.76114 1.96819L8.67224 2.35527C8.27043 2.02578 7.82175 1.76595 7.3369 1.58379L7.12662 0.445337C7.09447 0.269881 6.95652 0.133266 6.78106 0.101122L6.7449 0.0944249C6.04709 -0.031475 5.31312 -0.031475 4.61532 0.0944249L4.57915 0.101122C4.4037 0.133266 4.26574 0.269881 4.2336 0.445337L4.02198 1.58915C3.54115 1.7713 3.09514 2.0298 2.69601 2.35794L1.59908 1.96819C1.43166 1.90926 1.24415 1.95881 1.12896 2.09543L1.10485 2.12356C0.638756 2.67403 0.279807 3.2955 0.037383 3.97053L0.0253288 4.00536C-0.0349425 4.17278 0.0146139 4.36029 0.149889 4.47681L1.03789 5.23489C0.996365 5.48669 0.976275 5.74385 0.976275 5.99966C0.976275 6.25682 0.996365 6.51398 1.03789 6.76444L0.149889 7.52252C0.0146139 7.6377 -0.0349425 7.82521 0.0253288 7.99397L0.037383 8.0288C0.279807 8.70383 0.638756 9.32664 1.10485 9.87577L1.12896 9.9039C1.24415 10.0392 1.43032 10.0901 1.59908 10.0311L2.69601 9.64139C3.09514 9.96953 3.54115 10.2294 4.02198 10.4102L4.2336 11.554C4.26574 11.7294 4.4037 11.8661 4.57915 11.8982L4.61532 11.9049C4.96489 11.9679 5.3225 12 5.68011 12C6.03772 12 6.39667 11.9679 6.7449 11.9049L6.78106 11.8982C6.95652 11.8661 7.09447 11.7294 7.12662 11.554L7.3369 10.4155C7.82175 10.2334 8.27043 9.97489 8.67224 9.64406L9.76114 10.0311C9.92856 10.0901 10.1161 10.0405 10.2313 9.9039L10.2554 9.87577C10.7215 9.3253 11.0804 8.70383 11.3228 8.0288L11.3349 7.99397C11.3952 7.82923 11.3456 7.64172 11.2103 7.5252ZM9.3821 5.3849C9.41559 5.58714 9.433 5.79474 9.433 6.00234C9.433 6.20994 9.41559 6.41754 9.3821 6.61979L9.2937 7.15687L10.2942 8.01272C10.1429 8.3623 9.95133 8.69178 9.72364 8.99849L8.48071 8.55784L8.06015 8.9034C7.74005 9.16591 7.38378 9.37218 6.99804 9.51683L6.48774 9.70835L6.248 11.0075C5.87164 11.0504 5.48724 11.0504 5.10954 11.0075L4.8698 9.70568L4.36352 9.51147C3.9818 9.36682 3.62687 9.16056 3.30944 8.89938L2.88888 8.55249L1.63792 8.99715C1.41023 8.69044 1.22004 8.35962 1.06735 8.01138L2.07857 7.1475L1.99151 6.61175C1.95937 6.41219 1.94195 6.20593 1.94195 6.00234C1.94195 5.79742 1.95803 5.5925 1.99151 5.39293L2.07857 4.85719L1.06735 3.9933C1.2187 3.64373 1.41023 3.31425 1.63792 3.00753L2.88888 3.4522L3.30944 3.10531C3.62687 2.84413 3.9818 2.63787 4.36352 2.49322L4.87113 2.30169L5.11088 0.999833C5.48724 0.956973 5.87164 0.956973 6.24934 0.999833L6.48908 2.29901L6.99938 2.49054C7.38378 2.63519 7.74138 2.84145 8.06149 3.10397L8.48205 3.44952L9.72498 3.00887C9.95267 3.31559 10.1429 3.64641 10.2955 3.99464L9.29504 4.85049L9.3821 5.3849Z"
                fill="currentColor"
              />
              <path
                d="M5.67993 3.52136C4.38029 3.52136 3.32666 4.57145 3.32666 5.86674C3.32666 7.16202 4.38029 8.21211 5.67993 8.21211C6.97958 8.21211 8.03321 7.16202 8.03321 5.86674C8.03321 4.57145 6.97958 3.52136 5.67993 3.52136ZM6.73891 6.92215C6.45544 7.20333 6.07972 7.35925 5.67993 7.35925C5.28014 7.35925 4.90442 7.20333 4.62096 6.92215C4.33884 6.63964 4.1824 6.26518 4.1824 5.86674C4.1824 5.46829 4.33884 5.09383 4.62096 4.81132C4.90442 4.52881 5.28014 4.37423 5.67993 4.37423C6.07972 4.37423 6.45544 4.52881 6.73891 4.81132C7.02103 5.09383 7.17747 5.46829 7.17747 5.86674C7.17747 6.26518 7.02103 6.63964 6.73891 6.92215Z"
                fill="currentColor"
              />
            </svg>
          </button>
          <span className="header-util__sep" aria-hidden />
          {!agentPinned ? (
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
          ) : null}
        </div>
      </div>
    </header>
  );
}
