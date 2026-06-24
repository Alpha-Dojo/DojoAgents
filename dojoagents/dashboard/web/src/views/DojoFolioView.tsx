import { FolioHoldingsPanel } from '../components/DojoFolio/FolioHoldingsPanel';
import { FolioOverviewPanel } from '../components/DojoFolio/FolioOverviewPanel';
import { FolioPortfolioSidebar } from '../components/DojoFolio/FolioPortfolioSidebar';
import { useFolioPortfolios } from '../hooks/useFolioPortfolios';
import { useTranslation } from '../hooks/useTranslation';
import './DojoFolioView.css';

export function DojoFolioView() {
  const { t } = useTranslation();
  const {
    portfolios,
    allPortfolios,
    holdingsByPortfolioId,
    activePortfolio,
    activeId,
    setActiveId,
    setSearchQuery,
    listLoading,
    detailLoading,
    renamePortfolio,
    applyPortfolioConfig,
    applyShareOverrides,
    applyOpenDate,
    createPortfolio,
    deletePortfolio,
    addHolding,
    autoAllocate,
    addingTicker,
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
          onSelect={setActiveId}
          onRename={renamePortfolio}
          onDelete={deletePortfolio}
          onCreate={createPortfolio}
          onSearchQueryChange={setSearchQuery}
        />

        {activePortfolio ? (
          <>
            <FolioOverviewPanel
              portfolio={activePortfolio}
              loading={detailLoading}
              onApplyConfig={(config) => applyPortfolioConfig(activePortfolio.id, config)}
            />
            <FolioHoldingsPanel
              portfolio={activePortfolio}
              loading={detailLoading}
              addingTicker={addingTicker}
              allocating={detailLoading}
              onApplyShares={(shares, manualShares) =>
                applyShareOverrides(activePortfolio.id, shares, manualShares)
              }
              onApplyOpenDate={(ticker, openDate) =>
                applyOpenDate(activePortfolio.id, ticker, openDate)
              }
              onAddHolding={(ticker, market) => addHolding(activePortfolio.id, ticker, market)}
              onAutoAllocate={(market) => autoAllocate(activePortfolio.id, market)}
            />
          </>
        ) : (
          <div className="folio-main-empty folio-card">
            <p className="folio-main-empty__text">
              {listLoading ? t('folio.loading') : t('folio.selectOrCreate')}
            </p>
          </div>
        )}
      </div>
    </section>
  );
}
