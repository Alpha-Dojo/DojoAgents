import { useState } from 'react';
import type { FolioPortfolioDetail } from '../../api/dojoFolio';
import type { AppTab } from '../../navigation/appTab';
import type { FolioAllocationStrategy } from '../../types/dojoFolio';
import type { MarketCode } from '../../types/dojoMesh';
import { useTranslation } from '../../hooks/useTranslation';
import { FolioHoldingsPanel } from './FolioHoldingsPanel';
import { FolioReturnAttributionPanel } from './FolioReturnAttributionPanel';
import { FolioRiskExposurePanel } from './FolioRiskExposurePanel';

type FolioDetailTab = 'holdings' | 'attribution' | 'risk';

interface FolioDetailTabsProps {
  portfolio: FolioPortfolioDetail;
  loading?: boolean;
  addingTicker?: boolean;
  removingTicker?: string | null;
  allocating?: boolean;
  benchmarkSymbol: string | null;
  benchmarkLabel: string;
  onNavigateTab?: (tab: AppTab) => void;
  onApplyShares: (sharesByTicker: Record<string, number>) => void;
  onToggleSharesLock: (ticker: string, locked: boolean) => void;
  onToggleOpenDateLock: (ticker: string, locked: boolean) => void;
  onToggleCostLock: (ticker: string, locked: boolean) => void;
  onApplyCost: (ticker: string, cost: number | null) => void;
  onApplyOpenDate: (ticker: string, openDate: string | null) => void;
  onAddHolding: (ticker: string, market: MarketCode) => void;
  onRemoveHolding: (ticker: string, market: MarketCode) => void;
  onAutoAllocate: (market: MarketCode, strategy: FolioAllocationStrategy) => void;
}

export function FolioDetailTabs({
  portfolio,
  loading = false,
  addingTicker = false,
  removingTicker = null,
  allocating = false,
  benchmarkSymbol,
  benchmarkLabel,
  onNavigateTab,
  onApplyShares,
  onToggleSharesLock,
  onToggleOpenDateLock,
  onToggleCostLock,
  onApplyCost,
  onApplyOpenDate,
  onAddHolding,
  onRemoveHolding,
  onAutoAllocate,
}: FolioDetailTabsProps) {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<FolioDetailTab>('holdings');

  const tabs: Array<{ id: FolioDetailTab; label: string }> = [
    { id: 'holdings', label: t('folio.holdingsTitle') },
    { id: 'attribution', label: t('folio.attributionTitle') },
    { id: 'risk', label: t('folio.riskExposureTitle') },
  ];

  return (
    <article className="folio-card folio-detail-tabs">
      <header className="folio-detail-tabs__head">
        <div className="folio-detail-tabs__tabs" role="tablist" aria-label={t('folio.detailTabsLabel')}>
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              id={`folio-tab-${tab.id}`}
              aria-selected={activeTab === tab.id}
              aria-controls={`folio-panel-${tab.id}`}
              className={`folio-detail-tabs__tab${activeTab === tab.id ? ' folio-detail-tabs__tab--active' : ''}`}
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </header>

      <div className="folio-detail-tabs__body">
        {activeTab === 'holdings' ? (
          <div
            id="folio-panel-holdings"
            role="tabpanel"
            aria-labelledby="folio-tab-holdings"
            className="folio-detail-tabs__panel"
          >
            <FolioHoldingsPanel
              embedded
              portfolio={portfolio}
              loading={loading}
              addingTicker={addingTicker}
              removingTicker={removingTicker}
              allocating={allocating}
              onNavigateTab={onNavigateTab}
              onApplyShares={onApplyShares}
              onToggleSharesLock={onToggleSharesLock}
              onToggleOpenDateLock={onToggleOpenDateLock}
              onToggleCostLock={onToggleCostLock}
              onApplyCost={onApplyCost}
              onApplyOpenDate={onApplyOpenDate}
              onAddHolding={onAddHolding}
              onRemoveHolding={onRemoveHolding}
              onAutoAllocate={onAutoAllocate}
            />
          </div>
        ) : null}
        {activeTab === 'attribution' ? (
          <div
            id="folio-panel-attribution"
            role="tabpanel"
            aria-labelledby="folio-tab-attribution"
            className="folio-detail-tabs__panel folio-detail-tabs__panel--scroll"
          >
            <FolioReturnAttributionPanel
              portfolio={portfolio}
              loading={loading}
              benchmarkSymbol={benchmarkSymbol}
              benchmarkLabel={benchmarkLabel}
            />
          </div>
        ) : null}
        {activeTab === 'risk' ? (
          <div
            id="folio-panel-risk"
            role="tabpanel"
            aria-labelledby="folio-tab-risk"
            className="folio-detail-tabs__panel folio-detail-tabs__panel--scroll"
          >
            <FolioRiskExposurePanel
              portfolio={portfolio}
              loading={loading}
              benchmarkSymbol={benchmarkSymbol}
            />
          </div>
        ) : null}
      </div>
    </article>
  );
}
