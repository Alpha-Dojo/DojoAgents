import { useEffect, useMemo, useState } from 'react';
import { fetchBenchmarkCatalog, type BenchmarkCatalogResponse } from '../../api/market';
import { useTranslation } from '../../hooks/useTranslation';
import type { AppTab } from '../../navigation/appTab';
import type { FolioPortfolioDetail } from '../../api/folio';
import type { MarketCode } from '../../types/market';
import type { FolioAllocationStrategy, FolioCreateOrderPayload, FolioPortfolioConfig } from '../../types/folio';
import { DEFAULT_FOLIO_CONFIG } from '../../types/folio';
import { portfolioDefaultConfig } from '../../utils/folioStartDate';
import { buildFolioCandidateIndexOptions, resolveFolioBenchmarkLabel } from '../../utils/folioCandidateIndex';
import {
  findFolioBenchmarkOption,
  flattenFolioBenchmarkOptions,
  buildRebasedBenchmarkSeriesBySymbol,
  buildFolioBenchmarkHeadChips,
} from '../../utils/folioBenchmarkSeries';
import { MARKET_CODE } from '../../utils/marketDisplay';
import {
  FolioBenchmarkMultiSelect,
  type FolioBenchmarkMultiSelectEntry,
} from './FolioBenchmarkMultiSelect';
import { FolioDetailTabs } from './FolioDetailTabs';
import { FolioInlineConfig } from './FolioInlineConfig';
import { pickWindowMasterSeries } from '../../utils/folioNavWindow';
import { resolveFolioConfigMarkets } from '../../utils/folioConfigMarkets';
import { FolioNavCurveSection, type FolioNavCurveHeadContext } from './FolioNavCurveChart';
import { useFolioDetailSplit } from '../../hooks/useFolioDetailSplit';
import type { FolioPerformanceView } from '../../types/folio';

interface FolioOverviewBenchmarkSelectProps {
  head: FolioNavCurveHeadContext;
  performance: FolioPerformanceView | null | undefined;
  primaryBenchmarkSymbol: string;
  benchmarkSymbols: string[];
  benchmarkCatalog: BenchmarkCatalogResponse | null;
  options: FolioBenchmarkMultiSelectEntry[];
  candidateIndexLabel: (market: MarketCode) => string;
  locale: 'zh' | 'en';
  ariaLabel: string;
  onSelect: (symbol: string) => void;
}

function FolioOverviewBenchmarkSelect({
  head,
  performance,
  primaryBenchmarkSymbol,
  benchmarkSymbols,
  benchmarkCatalog,
  options,
  candidateIndexLabel,
  locale,
  ariaLabel,
  onSelect,
}: FolioOverviewBenchmarkSelectProps) {
  const anchorDate = head.hoverDate ?? head.anchorDate;

  const returnValue = useMemo(() => {
    const masterDates =
      pickWindowMasterSeries(head.windowRebasedByMarket)?.series.map((point) => point.date) ?? [];
    if (!primaryBenchmarkSymbol || masterDates.length === 0) return null;
    const rebasedBySymbol = buildRebasedBenchmarkSeriesBySymbol(
      [primaryBenchmarkSymbol],
      benchmarkCatalog,
      masterDates,
      performance,
    );
    const chips = buildFolioBenchmarkHeadChips(
      [primaryBenchmarkSymbol],
      benchmarkCatalog,
      rebasedBySymbol,
      anchorDate,
      candidateIndexLabel,
      locale,
    );
    return chips[0]?.value ?? null;
  }, [
    anchorDate,
    benchmarkCatalog,
    candidateIndexLabel,
    head.windowRebasedByMarket,
    locale,
    performance,
    primaryBenchmarkSymbol,
  ]);

  return (
    <FolioBenchmarkMultiSelect
      singleSelect
      variant="inline"
      aria-label={ariaLabel}
      className="folio-performance__benchmark-select"
      options={options}
      selected={benchmarkSymbols}
      returnValue={returnValue}
      onSelect={onSelect}
      onToggle={onSelect}
    />
  );
}

interface FolioOverviewPanelProps {
  portfolio: FolioPortfolioDetail;
  loading?: boolean;
  performanceLoading?: boolean;
  addingTicker?: boolean;
  removingTicker?: string | null;
  placingOrder?: boolean;
  allocating?: boolean;
  benchmarkSymbols: string[];
  onSelectBenchmark: (symbol: string) => void;
  onSetBenchmarkSymbols: (symbols: string[]) => void;
  onApplyConfig: (config: FolioPortfolioConfig) => void;
  onCreateOrder: (payload: FolioCreateOrderPayload) => Promise<void>;
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
  performanceLoading = false,
  addingTicker = false,
  removingTicker = null,
  placingOrder = false,
  allocating = false,
  benchmarkSymbols,
  onSelectBenchmark,
  onSetBenchmarkSymbols,
  onApplyConfig,
  onCreateOrder,
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
  const { t, text, locale } = useTranslation();
  const { splitRef, ratio, resizing, onResizeStart } = useFolioDetailSplit();
  const config = portfolio.config ?? portfolioDefaultConfig(portfolio, DEFAULT_FOLIO_CONFIG);
  const [draftConfig, setDraftConfig] = useState(config);
  const [benchmarkCatalog, setBenchmarkCatalog] = useState<BenchmarkCatalogResponse | null>(null);

  useEffect(() => {
    setDraftConfig(portfolio.config ?? portfolioDefaultConfig(portfolio, DEFAULT_FOLIO_CONFIG));
  }, [portfolio.config, portfolio.id, portfolio.positions, portfolio.orders]);

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
    () => JSON.stringify(draftConfig) !== JSON.stringify(portfolio.config ?? portfolioDefaultConfig(portfolio, DEFAULT_FOLIO_CONFIG)),
    [draftConfig, portfolio.config, portfolio.positions, portfolio.orders],
  );

  const benchmarkOptions = useMemo(
    () => flattenFolioBenchmarkOptions(benchmarkCatalog),
    [benchmarkCatalog],
  );

  const candidateIndexLabel = useMemo(
    () => (market: MarketCode) => t('folio.candidateIndexLabel', { market: MARKET_CODE[market] }),
    [t],
  );

  const defaultBenchmarkSymbol =
    portfolio.performance?.benchmarkSymbolByMarket?.us ?? benchmarkOptions[0]?.symbol ?? null;

  useEffect(() => {
    if (benchmarkSymbols.length > 0 || !defaultBenchmarkSymbol) return;
    onSetBenchmarkSymbols([defaultBenchmarkSymbol]);
  }, [benchmarkSymbols.length, defaultBenchmarkSymbol, onSetBenchmarkSymbols, portfolio.id]);

  const primaryBenchmarkSymbol = benchmarkSymbols[0] ?? defaultBenchmarkSymbol ?? '';

  const selectedBenchmarkLabel = useMemo(() => {
    const option = findFolioBenchmarkOption(benchmarkCatalog, primaryBenchmarkSymbol);
    return resolveFolioBenchmarkLabel(
      primaryBenchmarkSymbol,
      option,
      candidateIndexLabel,
      locale,
    );
  }, [benchmarkCatalog, candidateIndexLabel, locale, primaryBenchmarkSymbol]);

  const benchmarkMultiSelectOptions = useMemo((): FolioBenchmarkMultiSelectEntry[] => {
    const entries: FolioBenchmarkMultiSelectEntry[] = [];
    const candidateOptions = buildFolioCandidateIndexOptions(
      portfolio.performance,
      candidateIndexLabel,
    ).map((option) => ({
      kind: 'option' as const,
      symbol: option.symbol,
      label: option.label,
      market: option.market,
    }));

    const benchmarkEntries = benchmarkOptions.map((option) => ({
      kind: 'option' as const,
      symbol: option.symbol,
      label: text({ zh: option.labelZh, en: option.labelEn }),
      market: option.market,
    }));

    if (candidateOptions.length > 0) {
      entries.push({
        kind: 'header',
        id: 'candidate-index',
        label: t('folio.benchmarkGroupCandidate'),
      });
      entries.push(...candidateOptions);
    }
    if (benchmarkEntries.length > 0) {
      entries.push({
        kind: 'header',
        id: 'benchmark-index',
        label: t('folio.benchmarkGroupBenchmark'),
      });
      entries.push(...benchmarkEntries);
    }
    return entries;
  }, [benchmarkOptions, candidateIndexLabel, portfolio.performance, t, text]);

  const visibleConfigMarkets = useMemo(
    () => resolveFolioConfigMarkets(portfolio),
    [portfolio],
  );

  const handleApplyConfig = () => {
    onApplyConfig(draftConfig);
  };

  return (
    <section className="folio-overview">
      <div className="folio-overview__top">
        <div className="folio-overview__top-main">
          <FolioInlineConfig
            portfolio={portfolio}
            draftConfig={draftConfig}
            configDirty={configDirty}
            visibleMarkets={visibleConfigMarkets}
            onChange={setDraftConfig}
            onApply={handleApplyConfig}
          />
        </div>
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
              orders={portfolio.orders}
              loading={performanceLoading}
              benchmarkSymbols={benchmarkSymbols}
              benchmarkCatalog={benchmarkCatalog}
              visibleMarkets={visibleConfigMarkets}
              benchmarkControl={(head) => (
                <FolioOverviewBenchmarkSelect
                  head={head}
                  performance={portfolio.performance}
                  primaryBenchmarkSymbol={primaryBenchmarkSymbol}
                  benchmarkSymbols={benchmarkSymbols}
                  benchmarkCatalog={benchmarkCatalog}
                  options={benchmarkMultiSelectOptions}
                  candidateIndexLabel={candidateIndexLabel}
                  locale={locale}
                  ariaLabel={t('sectorPage.benchmarkLabel')}
                  onSelect={onSelectBenchmark}
                />
              )}
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
            placingOrder={placingOrder}
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
            onCreateOrder={onCreateOrder}
            onAutoAllocate={onAutoAllocate}
          />
        </div>
      </div>
    </section>
  );
}
