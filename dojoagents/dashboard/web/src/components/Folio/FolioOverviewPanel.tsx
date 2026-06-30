import { useEffect, useMemo, useRef, useState } from 'react';
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
import { FolioHeadlineMetrics } from './FolioHeadlineMetrics';
import { FolioInlineConfig } from './FolioInlineConfig';
import { pickWindowMasterSeries } from '../../utils/folioNavWindow';
import { FolioNavCurveSection, type FolioNavCurveHeadContext } from './FolioNavCurveChart';
import { useFolioDetailSplit } from '../../hooks/useFolioDetailSplit';
import type { FolioPerformanceView } from '../../types/folio';
import { DojoButton } from '../ui';

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
  const hasPortfolioContent = portfolio.candidates.length > 0 || portfolio.positions.length > 0;
  const [configExpanded, setConfigExpanded] = useState(false);
  const [benchmarkCatalog, setBenchmarkCatalog] = useState<BenchmarkCatalogResponse | null>(null);
  const prevContentCountRef = useRef(portfolio.candidates.length + portfolio.positions.length);

  useEffect(() => {
    setDraftConfig(portfolio.config ?? portfolioDefaultConfig(portfolio, DEFAULT_FOLIO_CONFIG));
  }, [portfolio.config, portfolio.id, portfolio.positions, portfolio.orders]);

  useEffect(() => {
    setConfigExpanded(false);
    prevContentCountRef.current = portfolio.candidates.length + portfolio.positions.length;
  }, [portfolio.id]);

  useEffect(() => {
    if (loading) return;
    const contentCount = portfolio.candidates.length + portfolio.positions.length;
    if (contentCount === 0) {
      setConfigExpanded(true);
    } else if (prevContentCountRef.current === 0 && contentCount > 0) {
      setConfigExpanded(false);
    }
    prevContentCountRef.current = contentCount;
  }, [loading, portfolio.candidates.length, portfolio.positions.length]);

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

  const showConfig = !loading && (hasPortfolioContent ? configExpanded : true);

  const handleApplyConfig = () => {
    onApplyConfig(draftConfig);
    if (hasPortfolioContent) {
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
            <FolioHeadlineMetrics portfolio={portfolio} loading={loading} />
          )}
        </div>

        <DojoButton
          icon
          size="sm"
          variant="secondary"
          className={`folio-config-toggle${showConfig ? ' folio-config-toggle--active is-active' : ''}${configDirty ? ' folio-config-toggle--dirty' : ''}`}
          aria-expanded={showConfig}
          aria-label={t('folio.openConfig')}
          title={t('folio.openConfig')}
          disabled={!hasPortfolioContent && !loading}
          onClick={() => {
            if (!hasPortfolioContent) return;
            setConfigExpanded((prev) => !prev);
          }}
        >
          <svg viewBox="0 0 12 12" fill="none" aria-hidden>
            <path
              d="M6 1.25v1.5M6 9.25v1.5M1.25 6h1.5M9.25 6h1.5M2.9 2.9l1.06 1.06M8.04 8.04l1.06 1.06M2.9 9.1l1.06-1.06M8.04 3.96l1.06-1.06"
              stroke="currentColor"
              strokeWidth="1.1"
              strokeLinecap="round"
            />
            <circle cx="6" cy="6" r="2.1" stroke="currentColor" strokeWidth="1.1" />
          </svg>
        </DojoButton>
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
              loading={loading}
              benchmarkSymbols={benchmarkSymbols}
              benchmarkCatalog={benchmarkCatalog}
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
