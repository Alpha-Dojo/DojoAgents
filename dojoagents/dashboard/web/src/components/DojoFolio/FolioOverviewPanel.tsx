import { useEffect, useMemo, useState } from 'react';
import { fetchBenchmarkCatalog, type BenchmarkCatalogResponse } from '../../api/dojoMesh';
import { useTranslation } from '../../hooks/useTranslation';
import type { AppTab } from '../../navigation/appTab';
import type { FolioPortfolioDetail } from '../../api/dojoFolio';
import type { MarketCode } from '../../types/dojoMesh';
import type { FolioAllocationStrategy, FolioPortfolioConfig } from '../../types/dojoFolio';
import { DEFAULT_FOLIO_CONFIG, FOLIO_MARKETS } from '../../types/dojoFolio';
import { FolioDetailTabs } from './FolioDetailTabs';
import { FolioMarketCapitalLabel } from './FolioMarketCapitalLabel';
import { FolioNavCurveSection } from './FolioNavCurveChart';
import { FolioRiskMetrics } from './FolioRiskMetrics';
import { FolioStartDatePicker } from './FolioStartDatePicker';
import { useFolioDetailSplit } from '../../hooks/useFolioDetailSplit';

interface FolioOverviewPanelProps {
  portfolio: FolioPortfolioDetail;
  loading?: boolean;
  addingTicker?: boolean;
  removingTicker?: string | null;
  allocating?: boolean;
  benchmarkSymbol: string | null;
  onBenchmarkChange: (symbol: string | null) => void;
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

function flattenBenchmarkOptions(catalog: BenchmarkCatalogResponse | null) {
  if (!catalog) return [] as Array<{ market: MarketCode; symbol: string; label: string }>;
  const options: Array<{ market: MarketCode; symbol: string; label: string }> = [];
  for (const market of FOLIO_MARKETS) {
    const group = catalog.markets[market];
    if (!group) continue;
    for (const item of group.benchmarks) {
      const label =
        typeof item.name === 'string'
          ? item.name
          : item.name?.zh || item.name?.en || item.symbol;
      options.push({ market, symbol: item.symbol, label });
    }
  }
  return options;
}

export function FolioOverviewPanel({
  portfolio,
  loading = false,
  addingTicker = false,
  removingTicker = null,
  allocating = false,
  benchmarkSymbol,
  onBenchmarkChange,
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
  const [benchmarkCatalog, setBenchmarkCatalog] = useState<BenchmarkCatalogResponse | null>(null);

  useEffect(() => {
    setDraftConfig(portfolio.config ?? DEFAULT_FOLIO_CONFIG);
  }, [portfolio.config, portfolio.id]);

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
    () => flattenBenchmarkOptions(benchmarkCatalog),
    [benchmarkCatalog],
  );

  const selectedBenchmark =
    benchmarkSymbol ??
    portfolio.performance?.benchmarkSymbolByMarket?.us ??
    benchmarkOptions[0]?.symbol ??
    '';

  const selectedBenchmarkLabel =
    benchmarkOptions.find((option) => option.symbol === selectedBenchmark)?.label ??
    selectedBenchmark;

  const updateCapital = (market: MarketCode, value: string) => {
    const parsed = Number(value.replace(/,/g, ''));
    setDraftConfig((prev) => ({
      ...prev,
      capitalByMarket: {
        ...prev.capitalByMarket,
        [market]: Number.isFinite(parsed) && parsed >= 0 ? parsed : 0,
      },
    }));
  };

  return (
    <section className="folio-overview">
      <article className="folio-card folio-config">
        <div className="folio-config__grid">
          <label className="folio-config__field">
            <span className="folio-config__label">{t('folio.openDate')}</span>
            <FolioStartDatePicker
              value={draftConfig.startDate}
              onChange={(openDate) =>
                setDraftConfig((prev) => ({
                  ...prev,
                  startDate: openDate,
                  costDate: openDate,
                }))
              }
            />
          </label>
          {FOLIO_MARKETS.map((market) => (
            <label key={market} className="folio-config__field">
              <span className="folio-config__label">
                <FolioMarketCapitalLabel market={market} />
              </span>
              <input
                type="number"
                min={0}
                step={10000}
                className="folio-config__input"
                value={draftConfig.capitalByMarket[market]}
                onChange={(event) => updateCapital(market, event.target.value)}
              />
            </label>
          ))}
          <button
            type="button"
            className="folio-config__apply"
            disabled={!configDirty}
            onClick={() => onApplyConfig(draftConfig)}
          >
            {t('folio.applyConfig')}
          </button>
        </div>
        <p className="folio-config__hint">{t('folio.configHint')}</p>
      </article>

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
              benchmarkSymbol={selectedBenchmark}
              benchmarkControl={
                <div className="folio-performance__controls">
                  <label className="folio-performance__benchmark">
                    <span className="folio-performance__benchmark-label">{t('sphere.benchmarkLabel')}</span>
                    <select
                      className="folio-performance__benchmark-select"
                      value={selectedBenchmark}
                      onChange={(event) => onBenchmarkChange(event.target.value || null)}
                    >
                      {benchmarkOptions.map((option) => (
                        <option key={`${option.market}-${option.symbol}`} value={option.symbol}>
                          {text({ zh: option.label, en: option.label })}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
              }
            />
          </div>
          <div className="folio-performance__metrics-block">
            <FolioRiskMetrics
              performance={portfolio.performance}
              loading={loading}
              benchmarkSymbol={selectedBenchmark}
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
            benchmarkSymbol={selectedBenchmark}
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
