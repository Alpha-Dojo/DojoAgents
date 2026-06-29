import { FolioOverviewPanel } from '../components/DojoFolio/FolioOverviewPanel';
import { FolioPortfolioSidebar } from '../components/DojoFolio/FolioPortfolioSidebar';
import { LoadingIndicator } from '../components/ui/LoadingIndicator';
import { useFolioPortfolios } from '../hooks/useFolioPortfolios';
import { useTranslation } from '../hooks/useTranslation';
import type { AppTab } from '../navigation/appTab';
import './DojoFolioView.css';

interface DojoFolioViewProps {
  onNavigateTab?: (tab: AppTab) => void;
}

export function DojoFolioView({ onNavigateTab }: DojoFolioViewProps) {
  const { t } = useTranslation();
  const {
    portfolios,
    allPortfolios,
    holdingsByPortfolioId,
    activePortfolio,
    activeId,
    setActiveId,
    setSearchQuery,
    benchmarkSymbol,
    setBenchmarkSymbol,
    listLoading,
    creatingPortfolio,
    createError,
    detailLoading,
    allocating,
    renamePortfolio,
    applyPortfolioConfig,
    applyShareOverrides,
    toggleSharesLock,
    toggleOpenDateLock,
    toggleCostLock,
    applyCost,
    togglePortfolioPin,
    applyOpenDate,
    createPortfolio,
    deletePortfolio,
    addHolding,
    removeHolding,
    autoAllocate,
    addingTicker,
    removingTicker,
  } = useFolioPortfolios();

  return (
    <section className="dojo-folio-view" aria-label="DojoFolio">
      <div className="dojo-folio-view__layout">
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
          onCreate={createPortfolio}
          onSearchQueryChange={setSearchQuery}
        />

        {activePortfolio ? (
          <FolioOverviewPanel
            portfolio={activePortfolio}
            loading={detailLoading}
            addingTicker={addingTicker}
            removingTicker={removingTicker}
            allocating={allocating}
            benchmarkSymbol={benchmarkSymbol}
            onBenchmarkChange={setBenchmarkSymbol}
            onApplyConfig={(config) => applyPortfolioConfig(activePortfolio.id, config)}
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
