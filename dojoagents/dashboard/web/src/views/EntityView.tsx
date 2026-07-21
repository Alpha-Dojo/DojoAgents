import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { fetchSectorConstituents } from '../api/sector';
import { EntitySnapshotPanel } from '../components/Entity/EntitySnapshotPanel';
import { EntityStockEventsPanel } from '../components/Entity/EntityStockEventsPanel';
import { EntityIncomeDistributionPanel } from '../components/Entity/EntityIncomeDistributionPanel';
import { EntityKlineChart } from '../components/Entity/EntityKlineChart';
import { EntityPeBandChart } from '../components/Entity/EntityPeBandChart';
import { EntityStockNewsPanel } from '../components/Entity/EntityStockNewsPanel';
import { EntityRevenueChart } from '../components/Entity/EntityRevenueChart';
import { getMockEntityAsset } from '../data/mockEntityAsset';
import { useEntityFinIndicators } from '../hooks/useEntityFinIndicators';
import { useEntityStockEvents } from '../hooks/useEntityStockEvents';
import { useEntityStockNews } from '../hooks/useEntityStockNews';
import { useEntityStockIncome } from '../hooks/useEntityStockIncome';
import { useEntityKline } from '../hooks/useEntityKline';
import { useEntityPeBand } from '../hooks/useEntityPeBand';
import { useEntityQuote } from '../hooks/useEntityQuote';
import { useEntitySectorOptions } from '../hooks/useEntitySectorOptions';
import { useEntityViewportLayout } from '../hooks/useEntityViewportLayout';
import { useSyncedChartSurfaceHeight } from '../hooks/useSyncedChartSurfaceHeight';
import { useEntitySectorPeMetrics } from '../hooks/useEntitySectorPeMetrics';
import { useSectorTaxonomy } from '../hooks/useSectorTaxonomy';
import { useTranslation } from '../hooks/useTranslation';
import type { AppTab } from '../navigation/appTab';
import { readEntityTickerContext, resolveEntityTickerContext, saveEntityTickerContext } from '../navigation/entityContext';
import { openSectorFromEntityCrumb } from '../navigation/openSector';
import type { EntityKlineInterval, EntityTickerSearchItem } from '../types/entity';
import type { MarketCode } from '../types/market';
import type { SectorLevelKey } from '../types/sector';
import type { SectorPathSelection } from '../types/sectorTaxonomy';
import {
  findSectorOptionIndex,
  selectionFromSectorOption,
} from '../utils/entitySectorOptions';
import {
  mapFinIndicatorsToFinancials,
  resolveNaturalMinusFiscalQuarters,
} from '../utils/entityFinIndicators';
import { buildEntityKeyMetrics, isEntityTtmPeLoss } from '../utils/entityKeyMetrics';
import { mapStockEventsToEntityItems } from '../utils/entityStockEvents';
import { mapStockNewsToEntityItems } from '../utils/entityStockNews';
import { buildEarningsEventsFromFinIndicators } from '../utils/entityChartEvents';
import {
  buildQuoteSnapshotFromKlineBars,
  resolveCoreDailyChartWindow,
  resolveLatestKlineAnchorDate,
  sliceCoreBarsToDateWindow,
} from '../utils/entityKline';
import { slicePePointsToDateWindow } from '../utils/entityPeBand';
import { formatKlineDate } from '../utils/klineDate';
import { findSectorPathByIds, getDefaultSelection } from '../utils/sectorTaxonomy';
import { scopeSectorName } from '../utils/sectorTitle';
import './EntityView.css';

type ChartLinkSource = 'kline' | 'pe';

interface EntityViewProps {
  onNavigateTab?: (tab: AppTab) => void;
}

export function EntityView({ onNavigateTab }: EntityViewProps) {
  const { t, locale } = useTranslation();
  const viewRef = useRef<HTMLElement>(null);
  const chartRowRef = useRef<HTMLDivElement>(null);
  const layoutVars = useEntityViewportLayout(viewRef);
  useSyncedChartSurfaceHeight(chartRowRef);
  const { taxonomy } = useSectorTaxonomy();
  const [ctx, setCtx] = useState(resolveEntityTickerContext);
  const [selection, setSelection] = useState<SectorPathSelection | null>(null);
  const [klineInterval, setKlineInterval] = useState<EntityKlineInterval>('1D');
  const [sectorPeLevel, setSectorPeLevel] = useState<SectorLevelKey>('L3');
  const [linkedHover, setLinkedHover] = useState<{ date: string; source: ChartLinkSource } | null>(
    null,
  );
  const sectorChangeRef = useRef(false);
  const initTickerKeyRef = useRef('');
  const pendingCycleRef = useRef(false);

  useEffect(() => {
    const refresh = () => setCtx(readEntityTickerContext() ?? resolveEntityTickerContext());
    window.addEventListener('alphadojo-entity-ticker', refresh);
    return () => window.removeEventListener('alphadojo-entity-ticker', refresh);
  }, []);

  const { sectorOptions, loading: sectorOptionsLoading, reload: reloadSectorOptions, optionsReady } =
    useEntitySectorOptions(ctx);
  const { data: finIndicators, loading: finIndicatorsLoading } = useEntityFinIndicators(ctx);
  const { data: stockIncome, loading: stockIncomeLoading } = useEntityStockIncome(ctx);
  const { data: stockEvents, loading: stockEventsLoading } = useEntityStockEvents(ctx, 20);
  const { data: stockNews, loading: stockNewsLoading } = useEntityStockNews(ctx, 20);
  const { bars: klineBars, loading: klineLoading, ready: klineReady, error: klineError } =
    useEntityKline(ctx, klineInterval);
  const { points: peBandPoints, loading: peBandLoading, ready: peBandReady, error: peBandError } =
    useEntityPeBand(ctx);
  const { detail: quoteDetail, ready: quoteReady } = useEntityQuote(ctx);
  const tickerKey = ctx ? `${ctx.market ?? ''}:${ctx.ticker}` : '';

  useEffect(() => {
    if (!quoteReady || !quoteDetail) return;
    const current = readEntityTickerContext();
    if (!current) return;
    const { zh, en } = quoteDetail.name ?? {};
    const canonicalTicker = quoteDetail.ticker?.trim().toUpperCase();
    const nameChanged = Boolean(zh || en) && (current.name_zh !== zh || current.name_en !== en);
    const tickerChanged = Boolean(canonicalTicker) && current.ticker !== canonicalTicker;
    if (!nameChanged && !tickerChanged) return;
    const next = {
      ...current,
      ...(zh ? { name_zh: zh || current.name_zh } : {}),
      ...(en ? { name_en: en || current.name_en } : {}),
      ...(canonicalTicker ? { ticker: canonicalTicker } : {}),
    };
    saveEntityTickerContext(next);
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

  const { metrics: sectorMetrics, loading: sectorMetricsLoading } = useEntitySectorPeMetrics(resolvedSelection);

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
        saveEntityTickerContext({
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
      openSectorFromEntityCrumb(onNavigateTab, {
        level,
        name,
        level1Id: resolvedSelection.level1Id,
        level2Id: resolvedSelection.level2Id,
        level3Id: resolvedSelection.level3Id,
      });
    },
    [taxonomy, resolvedSelection, onNavigateTab],
  );

  const handleTickerSelect = useCallback((item: EntityTickerSearchItem) => {
    const next = {
      ticker: item.ticker,
      market: item.market,
      name_zh: item.name.zh,
      name_en: item.name.en,
      sector_source: 'search' as const,
    };
    saveEntityTickerContext(next);
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

  const peTtmLoss = useMemo(
    () => isEntityTtmPeLoss(finIndicators?.items ?? [], ctx?.market),
    [finIndicators?.items, ctx?.market],
  );

  const peBandLossOnly = peBandReady && peBandDisplayPoints.length === 0 && peTtmLoss;

  const peBandAxisDates = useMemo(
    () => klineDisplayBars.map((bar) => formatKlineDate(bar.date)),
    [klineDisplayBars],
  );

  const metricRows = useMemo(
    () =>
      buildEntityKeyMetrics({
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
    const mock = getMockEntityAsset(ctx);
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

  const naturalMinusFiscalQuarters = useMemo(
    () => resolveNaturalMinusFiscalQuarters(finIndicators?.items ?? []),
    [finIndicators?.items],
  );

  const chartEvents = useMemo(
    () => buildEarningsEventsFromFinIndicators(finIndicators?.items ?? []),
    [finIndicators?.items],
  );

  const stockEventItems = useMemo(
    () => mapStockEventsToEntityItems(stockEvents?.items ?? []),
    [stockEvents?.items],
  );

  const stockNewsItems = useMemo(
    () => mapStockNewsToEntityItems(stockNews?.items ?? []),
    [stockNews?.items],
  );

  const incomeDistributions = stockIncome?.distributions ?? [];
  const incomeReportDate = stockIncome?.report_date ?? null;

  if (!asset) {
    return (
      <section className="entity-view entity-view--empty" aria-label="Equities">
        <p className="entity-view__status">{t('entityPage.selectTicker')}</p>
      </section>
    );
  }

  return (
    <section
      ref={viewRef}
      className="entity-view"
      aria-label="Equities"
      style={layoutVars as CSSProperties}
    >
      <EntitySnapshotPanel
        asset={asset}
        orderTicker={quoteDetail?.ticker ?? ctx.ticker}
        orderPrice={quoteDetail?.last_price ?? asset.quote.price}
        taxonomy={taxonomy}
        selection={resolvedSelection}
        sectorOptions={sectorOptions}
        sectorOptionsLoading={sectorOptionsLoading}
        onSelectionChange={handleSectorChange}
        onOpenSphereLevel={handleOpenSphereLevel}
        onCycleSector={handleCycleSector}
        onTickerSelect={handleTickerSelect}
      />

      <div className="entity-view__grid">
        <div className="entity-view__chart-row" ref={chartRowRef}>
          <EntityKlineChart
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
          <EntityPeBandChart
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
            anchorDate={chartAnchorDate}
            axisDates={peBandAxisDates}
            lossLabel={t('valuation.peLoss')}
            lossOnly={peBandLossOnly}
          />
        </div>
        <EntityRevenueChart
          financials={financials}
          loading={finIndicatorsLoading}
          market={finIndicators?.market ?? ctx?.market ?? null}
          naturalMinusFiscalQuarters={naturalMinusFiscalQuarters}
        />
        <EntityIncomeDistributionPanel
          distributions={incomeDistributions}
          reportDate={incomeReportDate}
          loading={stockIncomeLoading}
        />
        <EntityStockEventsPanel events={stockEventItems} loading={stockEventsLoading} />
        <EntityStockNewsPanel items={stockNewsItems} loading={stockNewsLoading} />
      </div>
    </section>
  );
}
