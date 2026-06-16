import { useState } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import type { SectorLevelKey } from '../../types/dojoSphere';
import type { SectorPathSelection } from '../../types/sectorTaxonomy';
import { SphereConstituentsTable } from './SphereConstituentsTable';

export type SphereBottomTabId = 'constituents';

interface SphereBottomTab {
  id: SphereBottomTabId;
  labelKey: 'sphere.tabConstituents';
}

const BOTTOM_TABS: SphereBottomTab[] = [{ id: 'constituents', labelKey: 'sphere.tabConstituents' }];

import type { AppTab } from '../../navigation/appTab';

interface SphereBottomPanelProps {
  selection: SectorPathSelection;
  scope: SectorLevelKey;
  onNavigateTab?: (tab: AppTab) => void;
}

export function SphereBottomPanel({ selection, scope, onNavigateTab }: SphereBottomPanelProps) {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<SphereBottomTabId>('constituents');

  return (
    <article className="sphere-card sphere-table-card sphere-bottom-panel">
      <header className="sphere-bottom-panel__tabs" role="tablist" aria-label={t('sphere.bottomPanelTabs')}>
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
              {t(tab.labelKey)}
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
          <SphereConstituentsTable
            selection={selection}
            scope={scope}
            onNavigateTab={onNavigateTab}
          />
        ) : null}
      </div>
    </article>
  );
}
