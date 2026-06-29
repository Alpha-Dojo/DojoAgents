import { useState } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import type { SectorLevelKey } from '../../types/sector';
import type { SectorPathSelection } from '../../types/sectorTaxonomy';
import { SectorConstituentsTable } from './SectorConstituentsTable';

export type SphereBottomTabId = 'constituents';

interface SphereBottomTab {
  id: SphereBottomTabId;
}

const BOTTOM_TABS: SphereBottomTab[] = [{ id: 'constituents' }];

import type { AppTab } from '../../navigation/appTab';

interface SectorBottomPanelProps {
  selection: SectorPathSelection;
  scope: SectorLevelKey;
  onNavigateTab?: (tab: AppTab) => void;
}

export function SectorBottomPanel({ selection, scope, onNavigateTab }: SectorBottomPanelProps) {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<SphereBottomTabId>('constituents');

  return (
    <article className="sphere-card sphere-table-card sphere-bottom-panel">
      <header className="sphere-bottom-panel__tabs" role="tablist" aria-label={t('sectorPage.bottomPanelTabs')}>
        {BOTTOM_TABS.map((tab) => {
          const selected = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              id={`sphere-bottom-tab-${tab.id}`}
              aria-selected={selected}
              aria-controls={`sphere-bottom-panel-${tab.id}`}
              className={`sphere-bottom-panel__tab${selected ? ' sphere-bottom-panel__tab--active' : ''}`}
              onClick={() => setActiveTab(tab.id)}
            >
              {t('sectorPage.tabConstituentsWithLevel', { level: scope })}
            </button>
          );
        })}
      </header>

      <div
        id={`sphere-bottom-panel-${activeTab}`}
        role="tabpanel"
        aria-labelledby={`sphere-bottom-tab-${activeTab}`}
        className="sphere-bottom-panel__content"
      >
        {activeTab === 'constituents' ? (
          <SectorConstituentsTable
            selection={selection}
            scope={scope}
            onNavigateTab={onNavigateTab}
          />
        ) : null}
      </div>
    </article>
  );
}
