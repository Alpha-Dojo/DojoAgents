import { useCallback, useEffect, useState } from 'react';
import './App.css';
import { AgentModelProvider } from './agent/AgentModelContext';
import { AgentRunProvider } from './agent/AgentRunContext';
import { Header } from './components/Header';
import { DojoAgentPanel } from './components/DojoAgent/DojoAgentPanel';
import { LocaleProvider } from './i18n/LocaleContext';
import { useAppTab } from './hooks/useAppTab';
import type { AppTab } from './navigation/appTab';
import { DojoCoreView } from './views/DojoCoreView';
import { DojoFolioView } from './views/DojoFolioView';
import { DojoMeshView } from './views/DojoMeshView';
import { DojoSphereView } from './views/DojoSphereView';
import './styles/marketDirection.css';
import './styles/chartDate.css';
import './styles/panelTitle.css';

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
    case 'mesh':
      return (
        <div className="app-main__pane">
          <DojoMeshView onNavigateTab={onNavigateTab} agentOpen={agentVisible} />
        </div>
      );
    case 'sphere':
      return (
        <div className="app-main__pane">
          <DojoSphereView onNavigateTab={onNavigateTab} />
        </div>
      );
    case 'core':
      return (
        <div className="app-main__pane">
          <DojoCoreView onNavigateTab={onNavigateTab} />
        </div>
      );
    case 'folio':
      return (
        <div className="app-main__pane">
          <DojoFolioView onNavigateTab={onNavigateTab} />
        </div>
      );
    default:
      return null;
  }
}

export default function App() {
  const { tab, setTab } = useAppTab('mesh');
  const [userAgentOpen, setUserAgentOpen] = useState(false);
  const agentPinned = tab === 'folio';
  const agentVisible = agentPinned || userAgentOpen;

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
          />
          <main className="app-main" aria-label={tab}>
            <div className="app-main__content">
              <MainView tab={tab} onNavigateTab={navigateTab} agentVisible={agentVisible} />
            </div>
            <DojoAgentPanel
              open={agentVisible}
              pinned={agentPinned}
              interactive={!agentPinned}
              sourceTab={tab}
              onClose={handleAgentClose}
            />
          </main>
        </div>
        </AgentRunProvider>
      </AgentModelProvider>
    </LocaleProvider>
  );
}
