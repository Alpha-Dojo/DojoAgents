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
    allocating,
    placingOrder,
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
    autoAllocate,
    addingTicker,
    removingTicker,
  } = useFolioPortfolios();

  return (
    <section className="folio-view" aria-label="Portfolio">
      <div className="folio-view__layout">
        <FolioPortfolioSidebar
          portfolios={portfolios}
          allPortfolios={allPortfolios}
          holdingsByPortfolioId={holdingsByPortfolioId}
          activeId={activeId}
          loading={listLoading}
          creating={creatingPortfolio}
          createError={createError}
          onSelect={setActiveId}
          onRename={renamePortfolio}
          onDelete={deletePortfolio}
          onTogglePin={togglePortfolioPin}
          onPromoteToManual={promotePortfolioToManual}
          onCreate={createPortfolio}
          onSearchQueryChange={setSearchQuery}
        />

        {activePortfolio ? (
          <FolioOverviewPanel
            portfolio={activePortfolio}
            loading={detailLoading}
            addingTicker={addingTicker}
            removingTicker={removingTicker}
            placingOrder={placingOrder}
            allocating={allocating}
            benchmarkSymbols={benchmarkSymbols}
            onSelectBenchmark={selectBenchmarkSymbol}
            onSetBenchmarkSymbols={setBenchmarkSymbols}
            onApplyConfig={(config) => applyPortfolioConfig(activePortfolio.id, config)}
            onCreateOrder={(payload) => createOrder(activePortfolio.id, payload)}
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
