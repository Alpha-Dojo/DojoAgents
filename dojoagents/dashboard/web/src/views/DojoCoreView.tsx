import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { fetchSectorConstituents } from '../api/dojoSphere';
import { CoreAssetSnapshot } from '../components/DojoCore/CoreAssetSnapshot';
import { CoreStockEventsPanel } from '../components/DojoCore/CoreStockEventsPanel';
import { CoreIncomeDistributionPanel } from '../components/DojoCore/CoreIncomeDistributionPanel';
import { CoreKlineChart } from '../components/DojoCore/CoreKlineChart';
import { CorePeBandChart } from '../components/DojoCore/CorePeBandChart';
import { CoreStockNewsPanel } from '../components/DojoCore/CoreStockNewsPanel';
import { CoreRevenueChart } from '../components/DojoCore/CoreRevenueChart';
import { getMockCoreAsset } from '../data/mockCoreAsset';
import { useCoreFinIndicators } from '../hooks/useCoreFinIndicators';
import { useCoreStockEvents } from '../hooks/useCoreStockEvents';
import { useCoreStockNews } from '../hooks/useCoreStockNews';
import { useCoreStockIncome } from '../hooks/useCoreStockIncome';
import { useCoreKline } from '../hooks/useCoreKline';
import { useCorePeBand } from '../hooks/useCorePeBand';
import { useCoreQuote } from '../hooks/useCoreQuote';
import { useCoreSectorOptions } from '../hooks/useCoreSectorOptions';
import { useCoreViewportLayout } from '../hooks/useCoreViewportLayout';
import { useSyncedChartSurfaceHeight } from '../hooks/useSyncedChartSurfaceHeight';
import { useCoreSectorPeMetrics } from '../hooks/useCoreSectorPeMetrics';
import { useSectorTaxonomy } from '../hooks/useSectorTaxonomy';
import { useTranslation } from '../hooks/useTranslation';
import type { AppTab } from '../navigation/appTab';
import { readCoreTickerContext, resolveCoreTickerContext, saveCoreTickerContext } from '../navigation/coreContext';
import { openSphereFromCoreCrumb } from '../navigation/openSphereSector';
import type { CoreKlineInterval, CoreTickerSearchItem } from '../types/dojoCore';
import type { MarketCode } from '../types/dojoMesh';
import type { SectorLevelKey } from '../types/dojoSphere';
import type { SectorPathSelection } from '../types/sectorTaxonomy';
import {
  findSectorOptionIndex,
  selectionFromSectorOption,
} from '../utils/coreSectorOptions';
import {
  mapFinIndicatorsToFinancials,
} from '../utils/coreFinIndicators';
import { buildCoreKeyMetrics } from '../utils/coreKeyMetrics';
import { mapStockEventsToCoreItems } from '../utils/coreStockEvents';
import { mapStockNewsToCoreItems } from '../utils/coreStockNews';
import { buildEarningsEventsFromFinIndicators } from '../utils/coreChartEvents';
import {
  buildQuoteSnapshotFromKlineBars,
  resolveCoreDailyChartWindow,
  resolveLatestKlineAnchorDate,
  sliceCoreBarsToDateWindow,
} from '../utils/coreKline';
import { slicePePointsToDateWindow } from '../utils/corePeBand';
import { findSectorPathByIds, getDefaultSelection } from '../utils/sectorTaxonomy';
import { scopeSectorName } from '../utils/sphereSectorTitle';
import './DojoCoreView.css';

type ChartLinkSource = 'kline' | 'pe';

interface DojoCoreViewProps {
  onNavigateTab?: (tab: AppTab) => void;
}

export function DojoCoreView({ onNavigateTab }: DojoCoreViewProps) {
  const { t, locale } = useTranslation();
  const viewRef = useRef<HTMLElement>(null);
  const chartRowRef = useRef<HTMLDivElement>(null);
  const layoutVars = useCoreViewportLayout(viewRef);
  useSyncedChartSurfaceHeight(chartRowRef);
  const { taxonomy } = useSectorTaxonomy();
  const [ctx, setCtx] = useState(resolveCoreTickerContext);
  const [selection, setSelection] = useState<SectorPathSelection | null>(null);
  const [klineInterval, setKlineInterval] = useState<CoreKlineInterval>('1D');
  const [sectorPeLevel, setSectorPeLevel] = useState<SectorLevelKey>('L3');
  const [linkedHover, setLinkedHover] = useState<{ date: string; source: ChartLinkSource } | null>(
    null,
  );
  const sectorChangeRef = useRef(false);
  const initTickerKeyRef = useRef('');
  const pendingCycleRef = useRef(false);

  useEffect(() => {
    const refresh = () => setCtx(readCoreTickerContext() ?? resolveCoreTickerContext());
    window.addEventListener('alphadojo-core-ticker', refresh);
    return () => window.removeEventListener('alphadojo-core-ticker', refresh);
  }, []);

  const { sectorOptions, loading: sectorOptionsLoading, reload: reloadSectorOptions, optionsReady } =
    useCoreSectorOptions(ctx);
  const { data: finIndicators, loading: finIndicatorsLoading } = useCoreFinIndicators(ctx);
  const { data: stockIncome, loading: stockIncomeLoading } = useCoreStockIncome(ctx);
  const { data: stockEvents, loading: stockEventsLoading } = useCoreStockEvents(ctx, 20);
  const { data: stockNews, loading: stockNewsLoading } = useCoreStockNews(ctx, 20);
  const { bars: klineBars, loading: klineLoading, ready: klineReady, error: klineError } =
    useCoreKline(ctx, klineInterval);
  const { points: peBandPoints, loading: peBandLoading, ready: peBandReady, error: peBandError } =
    useCorePeBand(ctx);
  const { detail: quoteDetail, ready: quoteReady } = useCoreQuote(ctx);
  const tickerKey = ctx ? `${ctx.market ?? ''}:${ctx.ticker}` : '';

  useEffect(() => {
    if (!quoteReady || !quoteDetail?.name) return;
    const current = readCoreTickerContext();
    if (!current) return;
    const { zh, en } = quoteDetail.name;
    if (!zh && !en) return;
    if (current.name_zh === zh && current.name_en === en) return;
    const next = { ...current, name_zh: zh || current.name_zh, name_en: en || current.name_en };
    saveCoreTickerContext(next);
    setCtx(next);
  }, [quoteReady, quoteDetail, tickerKey]);

  useEffect(() => {
    initTickerKeyRef.current = '';
    setSelection(null);
    pendingCycleRef.current = false;
    setKlineInterval('1D');
    setSectorPeLevel('L3');
    setLinkedHover(null);
  }, [tickerKey]);

  useEffect(() => {
    if (!ctx || !tickerKey || !optionsReady || !sectorOptions.length) return;
    if (initTickerKeyRef.current === tickerKey) return;
    initTickerKeyRef.current = tickerKey;

    if (ctx.sector_source === 'navigation' && ctx.sector_selection) {
      setSelection(ctx.sector_selection);
      return;
    }

    setSelection(selectionFromSectorOption(sectorOptions[0]));
  }, [ctx, tickerKey, sectorOptions, optionsReady]);

  const resolvedSelection = useMemo(() => {
    if (selection?.level1Id && selection.level2Id && selection.level3Id) {
      return selection;
    }
    if (ctx?.ticker && !optionsReady) return null;
    if (taxonomy) return getDefaultSelection(taxonomy);
    return null;
  }, [selection, taxonomy, optionsReady, ctx?.ticker]);

  const { metrics: sectorMetrics, loading: sectorMetricsLoading } = useCoreSectorPeMetrics(resolvedSelection);

  const sectorPath = useMemo(() => {
    if (!taxonomy || !resolvedSelection) return null;
    return findSectorPathByIds(taxonomy, resolvedSelection);
  }, [taxonomy, resolvedSelection]);

  const sectorLevelLabels = useMemo(() => {
    if (!sectorPath) return {} as Partial<Record<SectorLevelKey, string>>;
    const lang = locale === 'zh' ? 'zh' : 'en';
    return {
      L1: scopeSectorName(sectorPath, 'L1', lang),
      L2: scopeSectorName(sectorPath, 'L2', lang),
      L3: scopeSectorName(sectorPath, 'L3', lang),
    };
  }, [sectorPath, locale]);

  const sectorPeByMarket = useMemo(() => {
    const scope = sectorMetrics?.scopes?.[sectorPeLevel];
    if (!scope) return {} as Partial<Record<MarketCode, number | null>>;
    return {
      us: scope.us?.weighted_pe ?? null,
      cn: scope.cn?.weighted_pe ?? null,
      hk: scope.hk?.weighted_pe ?? null,
    };
  }, [sectorMetrics, sectorPeLevel]);

  const handleSectorChange = useCallback(
    async (next: SectorPathSelection) => {
      if (!ctx?.market) return;
      sectorChangeRef.current = true;
      setSelection(next);
      try {
        const constituents = await fetchSectorConstituents({
          level1Id: next.level1Id,
          level2Id: next.level2Id,
          level3Id: next.level3Id,
          market: ctx.market,
          scope: 'L3',
        });
        const stillListed = constituents.items.some((item) => item.ticker === ctx.ticker);
        if (stillListed) return;
        const fallback = constituents.items[0];
        if (!fallback) return;
        saveCoreTickerContext({
          ticker: fallback.ticker,
          market: fallback.market,
          name_zh: fallback.name.zh,
          name_en: fallback.name.en,
          sector_source: 'search',
        });
      } catch {
        // keep current ticker when constituent fetch fails
      }
    },
    [ctx?.market, ctx?.ticker],
  );

  const applyCycleSector = useCallback(() => {
    if (!resolvedSelection || sectorOptions.length < 2) return false;
    const activeIndex = findSectorOptionIndex(sectorOptions, resolvedSelection);
    const nextIndex = ((activeIndex >= 0 ? activeIndex : 0) + 1) % sectorOptions.length;
    sectorChangeRef.current = true;
    setSelection(selectionFromSectorOption(sectorOptions[nextIndex]));
    return true;
  }, [resolvedSelection, sectorOptions]);

  const handleCycleSector = useCallback(() => {
    if (applyCycleSector()) return;
    pendingCycleRef.current = true;
    reloadSectorOptions();
  }, [applyCycleSector, reloadSectorOptions]);

  useEffect(() => {
    if (!pendingCycleRef.current || sectorOptionsLoading) return;
    pendingCycleRef.current = false;
    applyCycleSector();
  }, [sectorOptionsLoading, sectorOptions, applyCycleSector]);

  const handleOpenSphereLevel = useCallback(
    (level: SectorLevelKey) => {
      if (!taxonomy || !resolvedSelection) return;
      const path = findSectorPathByIds(taxonomy, resolvedSelection);
      if (!path) return;
      const name =
        level === 'L1' ? path.level1.name : level === 'L2' ? path.level2.name : path.level3.name;
      openSphereFromCoreCrumb(onNavigateTab, {
        level,
        name,
        level1Id: resolvedSelection.level1Id,
        level2Id: resolvedSelection.level2Id,
        level3Id: resolvedSelection.level3Id,
      });
    },
    [taxonomy, resolvedSelection, onNavigateTab],
  );

  const handleTickerSelect = useCallback((item: CoreTickerSearchItem) => {
    const next = {
      ticker: item.ticker,
      market: item.market,
      name_zh: item.name.zh,
      name_en: item.name.en,
      sector_source: 'search' as const,
    };
    saveCoreTickerContext(next);
    setCtx(next);
  }, []);

  const dailyChartWindow = useMemo(() => {
    if (!ctx?.market) return null;
    return resolveCoreDailyChartWindow(ctx.market);
  }, [ctx?.market]);

  const klineDisplayBars = useMemo(() => {
    if (!klineReady || !ctx?.ticker) return [];
    let bars = klineBars;
    if (klineInterval === '1D' && dailyChartWindow) {
      bars = sliceCoreBarsToDateWindow(bars, dailyChartWindow);
    }
    return bars;
  }, [klineReady, klineBars, klineInterval, ctx?.ticker, dailyChartWindow]);

  const peBandDisplayPoints = useMemo(() => {
    if (!peBandReady || !ctx?.ticker) return [];
    let points = peBandPoints;
    if (dailyChartWindow) {
      points = slicePePointsToDateWindow(points, dailyChartWindow);
    }
    return points;
  }, [peBandReady, peBandPoints, ctx?.ticker, dailyChartWindow]);

  const chartAnchorDate = useMemo(
    () => resolveLatestKlineAnchorDate(klineDisplayBars),
    [klineDisplayBars],
  );

  const metricRows = useMemo(
    () =>
      buildCoreKeyMetrics({
        finRows: finIndicators?.items ?? [],
        klineBars: klineDisplayBars,
        peBandPoints: peBandDisplayPoints,
        chartAnchorDate,
        market: ctx?.market,
        peLossLabel: t('valuation.peLoss'),
        quoteDetail,
      }),
    [
      finIndicators?.items,
      klineDisplayBars,
      peBandDisplayPoints,
      chartAnchorDate,
      ctx?.market,
      quoteDetail,
      t,
    ],
  );

  const asset = useMemo(() => {
    if (!ctx) return null;
    const mock = getMockCoreAsset(ctx);
    const quote =
      buildQuoteSnapshotFromKlineBars(klineDisplayBars, ctx.market) ?? mock.quote;
    const name = quoteDetail?.name
      ? {
          zh: quoteDetail.name.zh || mock.name.zh,
          en: quoteDetail.name.en || mock.name.en,
        }
      : mock.name;

    return {
      ...mock,
      name,
      quote,
      metricRows,
    };
  }, [ctx, klineDisplayBars, metricRows, quoteDetail?.name]);

  const financials = useMemo(() => {
    return mapFinIndicatorsToFinancials(
      finIndicators?.items ?? [],
      finIndicators?.market,
    );
  }, [finIndicators?.items, finIndicators?.market]);

  const chartEvents = useMemo(
    () => buildEarningsEventsFromFinIndicators(finIndicators?.items ?? []),
    [finIndicators?.items],
  );

  const stockEventItems = useMemo(
    () => mapStockEventsToCoreItems(stockEvents?.items ?? []),
    [stockEvents?.items],
  );

  const stockNewsItems = useMemo(
    () => mapStockNewsToCoreItems(stockNews?.items ?? []),
    [stockNews?.items],
  );

  const incomeDistributions = stockIncome?.distributions ?? [];
  const incomeReportDate = stockIncome?.report_date ?? null;

  if (!asset) {
    return (
      <section className="dojo-core-view dojo-core-view--empty" aria-label="DojoCore">
        <p className="dojo-core-view__status">{t('core.selectTicker')}</p>
      </section>
    );
  }

  return (
    <section
      ref={viewRef}
      className="dojo-core-view"
      aria-label="DojoCore"
      style={layoutVars as CSSProperties}
    >
      <CoreAssetSnapshot
        asset={asset}
        taxonomy={taxonomy}
        selection={resolvedSelection}
        sectorOptions={sectorOptions}
        sectorOptionsLoading={sectorOptionsLoading}
        onSelectionChange={handleSectorChange}
        onOpenSphereLevel={handleOpenSphereLevel}
        onCycleSector={handleCycleSector}
        onTickerSelect={handleTickerSelect}
      />

      <div className="dojo-core-view__grid">
        <div className="dojo-core-view__chart-row" ref={chartRowRef}>
          <CoreKlineChart
            key={`kline:${tickerKey}`}
            chartKey={tickerKey}
            bars={klineDisplayBars}
            loading={klineLoading && !klineError && !klineReady}
            chartEvents={chartEvents}
            linkedHoverDate={linkedHover?.source === 'pe' ? linkedHover.date : null}
            onLinkedHoverDateChange={(date) =>
              setLinkedHover(date ? { date, source: 'kline' } : null)
            }
          />
          <CorePeBandChart
            key={`pe:${tickerKey}`}
            points={peBandDisplayPoints}
            loading={peBandLoading && !peBandError && !peBandReady}
            sectorPeByMarket={sectorPeByMarket}
            sectorPeLoading={sectorMetricsLoading}
            sectorPeLevel={sectorPeLevel}
            sectorLevelLabels={sectorLevelLabels}
            onSectorPeLevelChange={setSectorPeLevel}
            linkedHoverDate={linkedHover?.source === 'kline' ? linkedHover.date : null}
            onLinkedHoverDateChange={(date) =>
              setLinkedHover(date ? { date, source: 'pe' } : null)
            }
          />
        </div>
        <CoreRevenueChart
          financials={financials}
          loading={finIndicatorsLoading}
          market={finIndicators?.market ?? ctx?.market ?? null}
        />
        <CoreIncomeDistributionPanel
          distributions={incomeDistributions}
          reportDate={incomeReportDate}
          loading={stockIncomeLoading}
        />
        <CoreStockEventsPanel events={stockEventItems} loading={stockEventsLoading} />
        <CoreStockNewsPanel items={stockNewsItems} loading={stockNewsLoading} />
      </div>
    </section>
  );
}
