import { useState } from 'react';
import './App.css';
import { AgentModelProvider } from './agent/AgentModelContext';
import { Header } from './components/Header';
import { DojoAgentPanel } from './components/DojoAgent/DojoAgentPanel';
import { SettingsModal } from './components/settings/SettingsModal';
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
  agentOpen,
}: {
  tab: string;
  onNavigateTab: (tab: AppTab) => void;
  agentOpen: boolean;
}) {
  return (
    <>
      <div className="app-main__pane" hidden={tab !== 'mesh'} aria-hidden={tab !== 'mesh'}>
        <DojoMeshView onNavigateTab={onNavigateTab} agentOpen={agentOpen} />
      </div>
      <div className="app-main__pane" hidden={tab !== 'sphere'} aria-hidden={tab !== 'sphere'}>
        <DojoSphereView onNavigateTab={onNavigateTab} />
      </div>
      <div className="app-main__pane" hidden={tab !== 'core'} aria-hidden={tab !== 'core'}>
        <DojoCoreView onNavigateTab={onNavigateTab} />
      </div>
      <div className="app-main__pane" hidden={tab !== 'folio'} aria-hidden={tab !== 'folio'}>
        <DojoFolioView />
      </div>
    </>
  );
}

export default function App() {
  const { tab, setTab } = useAppTab('mesh');
  const [agentOpen, setAgentOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);

  return (
    <LocaleProvider>
      <AgentModelProvider>
        <div className="app">
          <Header
            activeTab={tab}
            onTabChange={setTab}
            agentOpen={agentOpen}
            onAgentToggle={() => setAgentOpen((open) => !open)}
            settingsOpen={settingsOpen}
            onSettingsOpen={() => setSettingsOpen(true)}
          />
          <main className="app-main" aria-label={tab}>
            <div className="app-main__content">
              <MainView tab={tab} onNavigateTab={setTab} agentOpen={agentOpen} />
            </div>
            <DojoAgentPanel open={agentOpen} onClose={() => setAgentOpen(false)} />
          </main>
          <SettingsModal open={settingsOpen} onClose={() => setSettingsOpen(false)} />
        </div>
      </AgentModelProvider>
    </LocaleProvider>
  );
}
