import { useEffect, useMemo, useRef, useState } from 'react';
import { fetchBenchmarkCatalog, type BenchmarkCatalogResponse } from '../../api/market';
import { useTranslation } from '../../hooks/useTranslation';
import type { AppTab } from '../../navigation/appTab';
import type { FolioPortfolioDetail } from '../../api/folio';
import type { MarketCode } from '../../types/market';
import type { FolioAllocationStrategy, FolioPortfolioConfig } from '../../types/folio';
import { DEFAULT_FOLIO_CONFIG } from '../../types/folio';
import { flattenFolioBenchmarkOptions } from '../../utils/folioBenchmarkSeries';
import { FolioBenchmarkMultiSelect } from './FolioBenchmarkMultiSelect';
import { FolioDetailTabs } from './FolioDetailTabs';
import { FolioHeadlineMetrics } from './FolioHeadlineMetrics';
import { FolioInlineConfig } from './FolioInlineConfig';
import { FolioNavCurveSection } from './FolioNavCurveChart';
import { FolioRiskMetrics } from './FolioRiskMetrics';
import { useFolioDetailSplit } from '../../hooks/useFolioDetailSplit';

interface FolioOverviewPanelProps {
  portfolio: FolioPortfolioDetail;
  loading?: boolean;
  addingTicker?: boolean;
  removingTicker?: string | null;
  allocating?: boolean;
  benchmarkSymbols: string[];
  onToggleBenchmark: (symbol: string) => void;
  onSetBenchmarkSymbols: (symbols: string[]) => void;
  onApplyConfig: (config: FolioPortfolioConfig) => void;
  onNavigateTab?: (tab: AppTab) => void;
  onApplyShares: (sharesByTicker: Record<string, number>) => void;
  onToggleSharesLock: (ticker: string, locked: boolean) => void;
  onToggleOpenDateLock: (ticker: string, locked: boolean) => void;
  onToggleCostLock: (ticker: string, locked: boolean) => void;
  onApplyCost: (ticker: string, cost: number | null) => void;
  onApplyOpenDate: (ticker: string, openDate: string | null) => void;
  onAddHolding: (ticker: string, market: MarketCode) => void;
  onRemoveHolding: (ticker: string, market: MarketCode) => void;
  onAutoAllocate: (strategy: FolioAllocationStrategy) => void;
}

export function FolioOverviewPanel({
  portfolio,
  loading = false,
  addingTicker = false,
  removingTicker = null,
  allocating = false,
  benchmarkSymbols,
  onToggleBenchmark,
  onSetBenchmarkSymbols,
  onApplyConfig,
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
}: FolioOverviewPanelProps) {
  const { t, text } = useTranslation();
  const { splitRef, ratio, resizing, onResizeStart } = useFolioDetailSplit();
  const config = portfolio.config ?? DEFAULT_FOLIO_CONFIG;
  const [draftConfig, setDraftConfig] = useState(config);
  const [configExpanded, setConfigExpanded] = useState(() => portfolio.holdings.length === 0);
  const [benchmarkCatalog, setBenchmarkCatalog] = useState<BenchmarkCatalogResponse | null>(null);
  const prevHoldingsCountRef = useRef(portfolio.holdings.length);

  useEffect(() => {
    setDraftConfig(portfolio.config ?? DEFAULT_FOLIO_CONFIG);
  }, [portfolio.config, portfolio.id]);

  useEffect(() => {
    setConfigExpanded(portfolio.holdings.length === 0);
    prevHoldingsCountRef.current = portfolio.holdings.length;
  }, [portfolio.id]);

  useEffect(() => {
    if (prevHoldingsCountRef.current === 0 && portfolio.holdings.length > 0) {
      setConfigExpanded(false);
    }
    prevHoldingsCountRef.current = portfolio.holdings.length;
  }, [portfolio.holdings.length]);

  useEffect(() => {
    let cancelled = false;
    void fetchBenchmarkCatalog()
      .then((response) => {
        if (!cancelled) setBenchmarkCatalog(response);
      })
      .catch(() => {
        if (!cancelled) setBenchmarkCatalog(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const configDirty = useMemo(
    () => JSON.stringify(draftConfig) !== JSON.stringify(portfolio.config ?? DEFAULT_FOLIO_CONFIG),
    [draftConfig, portfolio.config],
  );

  const benchmarkOptions = useMemo(
    () => flattenFolioBenchmarkOptions(benchmarkCatalog),
    [benchmarkCatalog],
  );

  const defaultBenchmarkSymbol =
    portfolio.performance?.benchmarkSymbolByMarket?.us ?? benchmarkOptions[0]?.symbol ?? null;

  useEffect(() => {
    if (benchmarkSymbols.length > 0 || !defaultBenchmarkSymbol) return;
    onSetBenchmarkSymbols([defaultBenchmarkSymbol]);
  }, [benchmarkSymbols.length, defaultBenchmarkSymbol, onSetBenchmarkSymbols, portfolio.id]);

  const primaryBenchmarkSymbol = benchmarkSymbols[0] ?? defaultBenchmarkSymbol ?? '';

  const selectedBenchmarkLabel =
    benchmarkOptions.find((option) => option.symbol === primaryBenchmarkSymbol)?.label ??
    primaryBenchmarkSymbol;

  const benchmarkMultiSelectOptions = useMemo(
    () =>
      benchmarkOptions.map((option) => ({
        symbol: option.symbol,
        label: text({ zh: option.label, en: option.label }),
        market: option.market,
      })),
    [benchmarkOptions, text],
  );

  const hasHoldings = portfolio.holdings.length > 0;
  const showConfig = configExpanded || !hasHoldings;

  const handleApplyConfig = () => {
    onApplyConfig(draftConfig);
    if (hasHoldings) {
      setConfigExpanded(false);
    }
  };

  return (
    <section className="folio-overview">
      <div className="folio-overview__top">
        <div className="folio-overview__top-main">
          {showConfig ? (
            <FolioInlineConfig
              draftConfig={draftConfig}
              configDirty={configDirty}
              onChange={setDraftConfig}
              onApply={handleApplyConfig}
            />
          ) : (
            <FolioHeadlineMetrics
              portfolio={portfolio}
              benchmarkSymbol={primaryBenchmarkSymbol}
              benchmarkLabel={selectedBenchmarkLabel}
              loading={loading}
            />
          )}
        </div>

        {hasHoldings ? (
          <button
            type="button"
            className={`folio-config-toggle${configExpanded ? ' folio-config-toggle--active' : ''}${configDirty ? ' folio-config-toggle--dirty' : ''}`}
            aria-expanded={configExpanded}
            aria-label={t('folio.openConfig')}
            title={t('folio.openConfig')}
            onClick={() => setConfigExpanded((prev) => !prev)}
          >
            <span className="folio-config-toggle__icon" aria-hidden>
              <svg width="13" height="13" viewBox="0 0 12 12" fill="none">
                <path
                  d="M6 1.25v1.5M6 9.25v1.5M1.25 6h1.5M9.25 6h1.5M2.9 2.9l1.06 1.06M8.04 8.04l1.06 1.06M2.9 9.1l1.06-1.06M8.04 3.96l1.06-1.06"
                  stroke="currentColor"
                  strokeWidth="1.1"
                  strokeLinecap="round"
                />
                <circle cx="6" cy="6" r="2.1" stroke="currentColor" strokeWidth="1.1" />
              </svg>
            </span>
          </button>
        ) : null}
      </div>

      <div
        ref={splitRef}
        className={`folio-overview__split${resizing ? ' folio-overview__split--resizing' : ''}`}
      >
        <article
          className="folio-card folio-performance folio-overview__performance"
          style={{ flexBasis: `${ratio * 100}%` }}
        >
          <div className="folio-performance__chart-block">
            <FolioNavCurveSection
              performance={portfolio.performance}
              loading={loading}
              benchmarkSymbols={benchmarkSymbols}
              benchmarkCatalog={benchmarkCatalog}
              benchmarkControl={
                <div className="folio-performance__controls">
                  <label className="folio-performance__benchmark">
                    <span className="folio-performance__benchmark-label">{t('sectorPage.benchmarkLabel')}</span>
                    <FolioBenchmarkMultiSelect
                      aria-label={t('sectorPage.benchmarkLabel')}
                      className="folio-performance__benchmark-select"
                      options={benchmarkMultiSelectOptions}
                      selected={benchmarkSymbols}
                      onToggle={onToggleBenchmark}
                    />
                  </label>
                </div>
              }
            />
          </div>
          <div className="folio-performance__metrics-block">
            <FolioRiskMetrics
              performance={portfolio.performance}
              loading={loading}
              benchmarkSymbol={primaryBenchmarkSymbol}
              benchmarkLabel={selectedBenchmarkLabel}
            />
          </div>
        </article>

        <div
          className="folio-overview__resize-handle"
          role="separator"
          aria-orientation="horizontal"
          aria-label={t('folio.resizeDetail')}
          title={t('folio.resizeDetail')}
          onPointerDown={onResizeStart}
        />

        <div className="folio-overview__detail">
          <FolioDetailTabs
            portfolio={portfolio}
            loading={loading}
            addingTicker={addingTicker}
            removingTicker={removingTicker}
            allocating={allocating}
            benchmarkSymbol={primaryBenchmarkSymbol}
            benchmarkLabel={selectedBenchmarkLabel}
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
      </div>
    </section>
  );
}
