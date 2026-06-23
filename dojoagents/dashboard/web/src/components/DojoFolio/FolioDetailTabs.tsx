import { useEffect, useState } from 'react';
import type { FolioPortfolioDetail } from '../../api/dojoFolio';
import { useTranslation } from '../../hooks/useTranslation';
import type { MarketCode } from '../../types/dojoMesh';
import {
  FolioHoldingsPanel,
  type FolioHoldingsEditorState,
} from './FolioHoldingsPanel';
import { FolioSectorAllocationPanel } from './FolioSectorAllocationPanel';

type FolioDetailTab = 'holdings' | 'sectors';

interface FolioDetailTabsProps {
  portfolio: FolioPortfolioDetail;
  loading?: boolean;
  addingTicker?: boolean;
  removingTicker?: string | null;
  allocating?: boolean;
  onApplyShares: (
    sharesByTicker: Record<string, number>,
    manualSharesByTicker: Record<string, boolean>,
  ) => void;
  onApplyOpenDate: (ticker: string, openDate: string | null) => void;
  onAddHolding: (ticker: string, market: MarketCode) => void;
  onRemoveHolding: (ticker: string, market: MarketCode) => void;
  onAutoAllocate: (market: MarketCode) => void;
}

export function FolioDetailTabs({
  portfolio,
  loading = false,
  addingTicker = false,
  removingTicker = null,
  allocating = false,
  onApplyShares,
  onApplyOpenDate,
  onAddHolding,
  onRemoveHolding,
  onAutoAllocate,
}: FolioDetailTabsProps) {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<FolioDetailTab>('holdings');
  const [holdingsEditor, setHoldingsEditor] = useState<FolioHoldingsEditorState | null>(null);

  useEffect(() => {
    if (activeTab !== 'holdings') {
      setHoldingsEditor(null);
    }
  }, [activeTab]);

  return (
    <article className="folio-card folio-detail-tabs">
      <header className="folio-detail-tabs__head">
        <div className="folio-detail-tabs__tabs" role="tablist" aria-label={t('folio.detailTabsLabel')}>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'holdings'}
            className={`folio-detail-tabs__tab${activeTab === 'holdings' ? ' folio-detail-tabs__tab--active' : ''}`}
            onClick={() => setActiveTab('holdings')}
          >
            {t('folio.holdingsTitle')}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'sectors'}
            className={`folio-detail-tabs__tab${activeTab === 'sectors' ? ' folio-detail-tabs__tab--active' : ''}`}
            onClick={() => setActiveTab('sectors')}
          >
            {t('folio.allocationTitle')}
          </button>
        </div>
        {activeTab === 'holdings' && holdingsEditor?.hasHoldings ? (
          <button
            type="button"
            className="folio-detail-tabs__confirm folio-holdings__confirm"
            disabled={!holdingsEditor.pendingChanges}
            onClick={holdingsEditor.onConfirm}
          >
            {t('folio.confirmShares')}
          </button>
        ) : null}
      </header>

      <div className="folio-detail-tabs__body">
        {activeTab === 'holdings' ? (
          <FolioHoldingsPanel
            embedded
            portfolio={portfolio}
            loading={loading}
            addingTicker={addingTicker}
            removingTicker={removingTicker}
            allocating={allocating}
            onApplyShares={onApplyShares}
            onApplyOpenDate={onApplyOpenDate}
            onAddHolding={onAddHolding}
            onRemoveHolding={onRemoveHolding}
            onAutoAllocate={onAutoAllocate}
            onEditorStateChange={setHoldingsEditor}
          />
        ) : (
          <FolioSectorAllocationPanel embedded holdings={portfolio.holdings} loading={loading} />
        )}
      </div>
    </article>
  );
}
