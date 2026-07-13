import { useCallback, useEffect, useState, lazy, Suspense } from 'react';
import './App.css';
import { AgentRunProvider } from './agent/AgentRunContext';
import { AgentModelProvider } from './agent/AgentModelContext';
import { Header } from './components/Header';
import { DojoAgentPanel } from './components/DojoAgent/DojoAgentPanel';
import { SettingsModal } from './components/settings/SettingsModal';
import { LocaleProvider } from './i18n/LocaleContext';
import { useAppTab } from './hooks/useAppTab';
import { useMarketDataRevisionSync } from './hooks/useMarketDataRevisionSync';
import type { AppTab } from './navigation/appTab';
import { LoadingIndicator } from './components/ui/LoadingIndicator';
import './styles/marketDirection.css';
import './styles/chartDate.css';
import './styles/panelTitle.css';
import './styles/uiPrimitives.css';

const EntityView = lazy(() => import('./views/EntityView').then(m => ({ default: m.EntityView })));
const FolioView = lazy(() => import('./views/FolioView').then(m => ({ default: m.FolioView })));
const MarketView = lazy(() => import('./views/MarketView').then(m => ({ default: m.MarketView })));
const SectorView = lazy(() => import('./views/SectorView').then(m => ({ default: m.SectorView })));


function MainView({
  tab,
  onNavigateTab,
  agentVisible,
}: {
  tab: AppTab;
  onNavigateTab: (tab: AppTab) => void;
  agentVisible: boolean;
}) {
  switch (tab) {
    case 'market':
      return (
        <div className="app-main__pane">
          <MarketView onNavigateTab={onNavigateTab} agentOpen={agentVisible} />
        </div>
      );
    case 'sector':
      return (
        <div className="app-main__pane">
          <SectorView onNavigateTab={onNavigateTab} />
        </div>
      );
    case 'entity':
      return (
        <div className="app-main__pane">
          <EntityView onNavigateTab={onNavigateTab} />
        </div>
      );
    case 'folio':
      return (
        <div className="app-main__pane">
          <FolioView onNavigateTab={onNavigateTab} />
        </div>
      );
    default:
      return null;
  }
}

export default function App() {
  const { tab, setTab } = useAppTab('folio');
  const [userAgentOpen, setUserAgentOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const agentPinned = tab === 'folio';
  const agentVisible = agentPinned || userAgentOpen;

  useMarketDataRevisionSync(true);

  const navigateTab = useCallback(
    (next: AppTab) => {
      if (next !== 'folio') {
        setUserAgentOpen(false);
      }
      setTab(next);
    },
    [setTab],
  );

  useEffect(() => {
    if (tab !== 'folio') {
      setUserAgentOpen(false);
    }
  }, [tab]);

  const handleAgentToggle = () => {
    if (agentPinned) return;
    setUserAgentOpen((open) => !open);
  };

  const handleAgentClose = () => {
    if (agentPinned) return;
    setUserAgentOpen(false);
  };

  return (
    <LocaleProvider>
      <AgentModelProvider>
        <AgentRunProvider>
          <div className="app">
            <Header
              activeTab={tab}
              onTabChange={navigateTab}
              agentOpen={agentVisible}
              agentPinned={agentPinned}
              onAgentToggle={handleAgentToggle}
              settingsOpen={settingsOpen}
              onSettingsOpen={() => setSettingsOpen(true)}
            />
            <main className="app-main" aria-label={tab}>
              <div className="app-main__content">
                <Suspense fallback={<LoadingIndicator variant="page" />}>
                  <MainView tab={tab} onNavigateTab={navigateTab} agentVisible={agentVisible} />
                </Suspense>
              </div>
                <DojoAgentPanel
                  open={agentVisible}
                  pinned={agentPinned}
                  interactive={!agentPinned}
                  sourceTab={tab}
                  onClose={handleAgentClose}
                />
            </main>
            <SettingsModal open={settingsOpen} onClose={() => setSettingsOpen(false)} />
          </div>
        </AgentRunProvider>
      </AgentModelProvider>
    </LocaleProvider>
  );
}
