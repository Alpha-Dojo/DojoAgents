import { useState } from 'react';
import type { FolioPortfolioDetail } from '../../api/folio';
import type { AppTab } from '../../navigation/appTab';
import type { FolioAllocationStrategy, FolioCreateOrderPayload, FolioOrderDraftContext } from '../../types/folio';
import type { MarketCode } from '../../types/market';
import { useTranslation } from '../../hooks/useTranslation';
import { FolioCandidatesPanel } from './FolioCandidatesPanel';
import { FolioCreateOrderModal } from './FolioCreateOrderModal';
import { FolioHoldingsPanel } from './FolioHoldingsPanel';
import { FolioReturnAttributionPanel } from './FolioReturnAttributionPanel';
import { FolioRiskExposurePanel } from './FolioRiskExposurePanel';

type FolioDetailTab = 'candidates' | 'positions' | 'performance' | 'risk';

interface FolioDetailTabsProps {
  portfolio: FolioPortfolioDetail;
  loading?: boolean;
  addingTicker?: boolean;
  removingTicker?: string | null;
  placingOrder?: boolean;
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
  onCreateOrder: (payload: FolioCreateOrderPayload) => Promise<void>;
  onAutoAllocate: (strategy: FolioAllocationStrategy) => void;
}

export function FolioDetailTabs({
  portfolio,
  loading = false,
  addingTicker = false,
  removingTicker = null,
  placingOrder = false,
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
  onCreateOrder,
}: FolioDetailTabsProps) {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<FolioDetailTab>('candidates');
  const [orderContext, setOrderContext] = useState<FolioOrderDraftContext | null>(null);

  const tabs: Array<{ id: FolioDetailTab; label: string }> = [
    { id: 'candidates', label: t('folio.tabCandidates') },
    { id: 'positions', label: t('folio.tabPositions') },
    { id: 'performance', label: t('folio.tabPerformance') },
    { id: 'risk', label: t('folio.tabRiskExposure') },
  ];

  const openCreateOrder = (context: FolioOrderDraftContext) => {
    setOrderContext(context);
  };

  return (
    <article className="folio-detail-tabs">
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
        {activeTab === 'candidates' ? (
          <div
            id="folio-panel-candidates"
            role="tabpanel"
            aria-labelledby="folio-tab-candidates"
            className="folio-detail-tabs__panel"
          >
            <FolioCandidatesPanel
              portfolio={portfolio}
              loading={loading}
              addingTicker={addingTicker}
              removingTicker={removingTicker}
              onNavigateTab={onNavigateTab}
              onAddCandidate={onAddHolding}
              onRemoveCandidate={onRemoveHolding}
              onCreateOrder={openCreateOrder}
            />
          </div>
        ) : null}
        {activeTab === 'positions' ? (
          <div
            id="folio-panel-positions"
            role="tabpanel"
            aria-labelledby="folio-tab-positions"
            className="folio-detail-tabs__panel"
          >
            <FolioHoldingsPanel
              embedded
              portfolio={portfolio}
              loading={loading}
              onNavigateTab={onNavigateTab}
              onApplyShares={onApplyShares}
              onToggleSharesLock={onToggleSharesLock}
              onToggleOpenDateLock={onToggleOpenDateLock}
              onToggleCostLock={onToggleCostLock}
              onApplyCost={onApplyCost}
              onApplyOpenDate={onApplyOpenDate}
              onCreateOrder={openCreateOrder}
            />
          </div>
        ) : null}
        {activeTab === 'performance' ? (
          <div
            id="folio-panel-performance"
            role="tabpanel"
            aria-labelledby="folio-tab-performance"
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

      <FolioCreateOrderModal
        open={orderContext != null}
        portfolioId={portfolio.id}
        context={orderContext}
        placing={placingOrder}
        onClose={() => setOrderContext(null)}
        onSubmit={onCreateOrder}
      />
    </article>
  );
}
