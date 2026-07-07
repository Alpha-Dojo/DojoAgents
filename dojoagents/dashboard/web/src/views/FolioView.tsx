import { useState } from 'react';
import { FolioOverviewPanel } from '../components/Folio/FolioOverviewPanel';
import { FolioPortfolioSidebar } from '../components/Folio/FolioPortfolioSidebar';
import { LoadingIndicator } from '../components/ui/LoadingIndicator';
import { useFolioPortfolios } from '../hooks/useFolioPortfolios';
import { useTranslation } from '../hooks/useTranslation';
import type { AppTab } from '../navigation/appTab';
import './FolioView.css';

interface FolioViewProps {
  onNavigateTab?: (tab: AppTab) => void;
}

export function FolioView({ onNavigateTab }: FolioViewProps) {
  const { t } = useTranslation();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const {
    portfolios,
    allPortfolios,
    holdingsByPortfolioId,
    activePortfolio,
    activeId,
    setActiveId,
    setSearchQuery,
    benchmarkSymbols,
    setBenchmarkSymbols,
    selectBenchmarkSymbol,
    listLoading,
    creatingPortfolio,
    createError,
    detailLoading,
    performanceLoading,
    allocating,
    placingOrder,
    syncingPosition,
    renamePortfolio,
    applyPortfolioConfig,
    applyShareOverrides,
    toggleSharesLock,
    toggleOpenDateLock,
    toggleCostLock,
    applyCost,
    togglePortfolioPin,
    promotePortfolioToManual,
    applyOpenDate,
    createPortfolio,
    deletePortfolio,
    addHolding,
    removeHolding,
    createOrder,
    syncPosition,
    autoAllocate,
    addingTicker,
    removingTicker,
  } = useFolioPortfolios();

  return (
    <section className="folio-view" aria-label="Portfolio">
      <div
        className={`folio-view__layout ${
          sidebarCollapsed ? 'folio-view__layout--sidebar-collapsed' : ''
        }`}
      >
        <FolioPortfolioSidebar
          portfolios={portfolios}
          allPortfolios={allPortfolios}
          holdingsByPortfolioId={holdingsByPortfolioId}
          activeId={activeId}
          loading={listLoading}
          creating={creatingPortfolio}
          createError={createError}
          collapsed={sidebarCollapsed}
          onSelect={setActiveId}
          onRename={renamePortfolio}
          onDelete={deletePortfolio}
          onTogglePin={togglePortfolioPin}
          onPromoteToManual={promotePortfolioToManual}
          onCreate={createPortfolio}
          onSearchQueryChange={setSearchQuery}
          onToggleCollapsed={() => setSidebarCollapsed((current) => !current)}
        />

        {activePortfolio ? (
          <FolioOverviewPanel
            portfolio={activePortfolio}
            loading={detailLoading}
            performanceLoading={performanceLoading}
            addingTicker={addingTicker}
            removingTicker={removingTicker}
            placingOrder={placingOrder}
            syncingPosition={syncingPosition}
            allocating={allocating}
            benchmarkSymbols={benchmarkSymbols}
            onSelectBenchmark={selectBenchmarkSymbol}
            onSetBenchmarkSymbols={setBenchmarkSymbols}
            onApplyConfig={(config) => applyPortfolioConfig(activePortfolio.id, config)}
            onCreateOrder={(payload) => createOrder(activePortfolio.id, payload)}
            onSyncPosition={(payload) => syncPosition(activePortfolio.id, payload)}
            onNavigateTab={onNavigateTab}
            onApplyShares={(shares) => applyShareOverrides(activePortfolio.id, shares)}
            onToggleSharesLock={(ticker, locked) =>
              toggleSharesLock(activePortfolio.id, ticker, locked)
            }
            onToggleOpenDateLock={(ticker, locked) =>
              toggleOpenDateLock(activePortfolio.id, ticker, locked)
            }
            onToggleCostLock={(ticker, locked) =>
              toggleCostLock(activePortfolio.id, ticker, locked)
            }
            onApplyCost={(ticker, cost) => applyCost(activePortfolio.id, ticker, cost)}
            onApplyOpenDate={(ticker, openDate) =>
              applyOpenDate(activePortfolio.id, ticker, openDate)
            }
            onAddHolding={(ticker, market) => addHolding(activePortfolio.id, ticker, market)}
            onRemoveHolding={(ticker, market) => removeHolding(activePortfolio.id, ticker, market)}
            onAutoAllocate={(strategy) => autoAllocate(activePortfolio.id, strategy)}
          />
        ) : (
          <div className="folio-main-empty folio-card">
            {listLoading ? (
              <LoadingIndicator label={t('folio.loading')} variant="page" />
            ) : (
              <p className="folio-main-empty__text">{t('folio.selectOrCreate')}</p>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
