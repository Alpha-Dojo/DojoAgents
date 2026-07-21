import { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchCrossMarketSectors,
  fetchSectorMoversLatestDate,
  MARKET_COLUMNS,
} from "../api/market";
import { AddMarketSlot } from "../components/Market/AddMarketSlot";
import { DraggableMarketColumn } from "../components/Market/DraggableMarketColumn";
import { useDailySectorDiscovery } from "../hooks/useDailySectorDiscovery";
import { useMarketDynamics } from "../hooks/useMarketDynamics";
import { useMarketOverview } from "../hooks/useMarketOverview";
import { useSectorTaxonomy } from "../hooks/useSectorTaxonomy";
import {
  MARKET_VIEW_NARROW_QUERY,
  useMediaQuery,
} from "../hooks/useMediaQuery";
import { useTranslation } from "../hooks/useTranslation";
import {
  readStoredMarketOrder,
  reorderMarkets,
  storeMarketOrder,
  type MarketDropSide,
} from "../navigation/marketColumnOrder";
import { saveSectorJumpContext } from "../navigation/sectorContext";
import { openEntityTicker } from "../navigation/openEntityTicker";
import { clearPersistedSectorViewState } from "../cache/sectorViewState";
import { cacheKeys } from "../cache/cacheKeys";
import { fetchCached, getCached } from "../cache/queryCache";
import { useMarketDataCacheEpoch } from "../hooks/useMarketDataCacheEpoch";
import {
  MarketSectorMoversBar,
  type MarketSectorTabId,
} from "../components/Market/MarketSectorMoversBar";
import { MarketColumnPanel } from "../components/Market/MarketColumnPanel";
import { MarketEventTimeline } from "../components/Market/MarketEventTimeline";
import { MarketSectorTreemap } from "../components/Market/MarketSectorTreemap";
import { LoadingIndicator } from "../components/ui/LoadingIndicator";
import type { AppTab } from "../navigation/appTab";
import type {
  MarketCode,
  SectorItem,
  SectorMemberItem,
} from "../types/market";
import type { CrossMarketLink, CrossMarketLookup } from "../utils/sectorLink";
import { sectorLinkKey } from "../utils/sectorLink";
import {
  findSectorPathByLinkKey,
  selectionFromPath,
} from "../utils/sectorTaxonomy";
import { resolveAlignedKlineYearWindowsFromBars } from "../utils/klineDate";
import {
  readMeshSectorFilters,
  storeMeshSectorFilters,
  type MeshSectorFilterState,
} from "../utils/marketSectorFilters";
import { toCalendarDate, addCalendarDays } from "../utils/marketDynamicsWindow";
import {
  dynamicsImpactToSectorItem,
  preferredImpactMarket,
} from "../utils/marketDynamicsSectorJump";
import type { MarketDynamicsSectorImpact } from "../types/marketDynamics";
import "./MarketView.css";
import "./../components/Market/MarketEventTimeline.css";

interface MarketViewProps {
  onNavigateTab?: (tab: AppTab) => void;
  agentOpen?: boolean;
}

export function MarketView({
  onNavigateTab,
  agentOpen = false,
}: MarketViewProps) {
  const { t } = useTranslation();
  const isNarrowLayout = useMediaQuery(MARKET_VIEW_NARROW_QUERY);
  const [sectorFilters, setSectorFilters] = useState<MeshSectorFilterState>(
    readMeshSectorFilters,
  );
  const [sectorTab, setSectorTab] = useState<MarketSectorTabId>("discovery");
  const [eventCategory, setEventCategory] = useState<string>("all");
  const [discoveryDate, setDiscoveryDate] = useState<string>("");
  const cacheEpoch = useMarketDataCacheEpoch();
  const moversAsOfKey = cacheKeys.marketSectorMoversAsOf();
  const [latestMoversDate, setLatestMoversDate] = useState<string>(
    () => toCalendarDate(getCached<string>(moversAsOfKey)),
  );
  const { data, loading, sectorsLoading, error, reload } = useMarketOverview(
    sectorFilters,
    { loadMeshMovers: sectorTab === "movers" },
  );
  const {
    events: dynamicsEvents,
    datasetStart,
    loading: dynamicsLoading,
    loadingMore: dynamicsLoadingMore,
    error: dynamicsError,
    hasMoreBefore,
    hasMoreAfter,
    reload: reloadDynamics,
    loadMoreBefore,
    loadMoreAfter,
  } = useMarketDynamics({ centerDate: discoveryDate });

  useEffect(() => {
    let cancelled = false;
    const cached = toCalendarDate(getCached<string>(moversAsOfKey));
    if (cached) setLatestMoversDate(cached);

    fetchCached(moversAsOfKey, async () => {
      const date = await fetchSectorMoversLatestDate();
      return date || "";
    })
      .then((date) => {
        if (!cancelled) setLatestMoversDate(toCalendarDate(date));
      })
      .catch(() => {
        if (!cancelled && !cached) setLatestMoversDate("");
      });

    return () => {
      cancelled = true;
    };
  }, [moversAsOfKey, cacheEpoch]);

  /**
   * Discovery defaults to sector-movers precompute latest day
   * (行业板块涨跌榜), not market overview `as_of` which can be ahead of precompute.
   */
  const latestTradingDay = useMemo(
    () => toCalendarDate(latestMoversDate),
    [latestMoversDate],
  );

  const discoveryMinDate = useMemo(() => {
    const start = toCalendarDate(datasetStart);
    if (start) return start;
    if (!latestTradingDay) return '';
    return addCalendarDays(latestTradingDay, -365) || latestTradingDay;
  }, [datasetStart, latestTradingDay]);

  const discoveryMaxDate = latestTradingDay;

  useEffect(() => {
    if (!latestTradingDay) return;
    setDiscoveryDate((prev) => {
      if (!prev) return latestTradingDay;
      // Keep in-range user picks; clamp only if bounds known and out of range.
      if (discoveryMinDate && prev < discoveryMinDate) return latestTradingDay;
      if (discoveryMaxDate && prev > discoveryMaxDate) return latestTradingDay;
      return prev;
    });
  }, [latestTradingDay, discoveryMinDate, discoveryMaxDate]);

  const treemapDate = discoveryDate || latestTradingDay;

  const {
    moves: discoveryMoves,
    loading: discoveryLoading,
    error: discoveryError,
    reload: reloadDiscovery,
  } = useDailySectorDiscovery({
    minCapYi: sectorFilters.minCapYi,
    asOfDate: treemapDate,
  });

  const filteredEvents = useMemo(() => {
    if (eventCategory === "all") return dynamicsEvents;
    return dynamicsEvents.filter(
      (event) => event.event_summary?.category === eventCategory,
    );
  }, [dynamicsEvents, eventCategory]);

  const discoveryMaxAbs = useMemo(
    () =>
      Math.max(
        ...discoveryMoves.map((move) => Math.abs(move.change_percent)),
        0.01,
      ),
    [discoveryMoves],
  );
  const { taxonomy } = useSectorTaxonomy();
  const [crossMarketLink, setCrossMarketLink] =
    useState<CrossMarketLink | null>(null);
  const [crossMarketLookup, setCrossMarketLookup] = useState<CrossMarketLookup>(
    {},
  );
  const [chartHoverDate, setChartHoverDate] = useState<string | null>(null);
  const [marketOrder, setMarketOrder] = useState<MarketCode[]>(
    readStoredMarketOrder,
  );
  const [draggingMarket, setDraggingMarket] = useState<MarketCode | null>(null);
  const [dropTargetMarket, setDropTargetMarket] = useState<MarketCode | null>(
    null,
  );
  const [dropTargetSide, setDropTargetSide] = useState<MarketDropSide | null>(
    null,
  );

  const orderedColumns = useMemo(() => {
    const metaByCode = new Map(
      MARKET_COLUMNS.map((column) => [column.code, column]),
    );
    return marketOrder
      .map((code) => metaByCode.get(code))
      .filter(
        (column): column is (typeof MARKET_COLUMNS)[number] =>
          column !== undefined,
      );
  }, [marketOrder]);

  const updateSectorFilters = useCallback(
    (patch: Partial<MeshSectorFilterState>) => {
      setSectorFilters((prev) => {
        const next = { ...prev, ...patch };
        storeMeshSectorFilters(next);
        return next;
      });
    },
    [],
  );

  const chartWindowsByMarket = useMemo(() => {
    if (!data)
      return {} as Partial<Record<MarketCode, { start: string; end: string }>>;
    const barsByMarket: Partial<Record<MarketCode, { datetime: string }[]>> =
      {};
    for (const code of ["us", "cn", "hk"] as MarketCode[]) {
      const column = data.markets[code];
      if (!column) continue;
      barsByMarket[code] = column.benchmarks.flatMap(
        (benchmark) => benchmark.kline,
      );
    }
    return resolveAlignedKlineYearWindowsFromBars(barsByMarket) as Partial<
      Record<MarketCode, { start: string; end: string }>
    >;
  }, [data]);

  const handleDragStart = useCallback((market: MarketCode) => {
    setDraggingMarket(market);
    setDropTargetMarket(null);
    setDropTargetSide(null);
  }, []);

  const handleDragEnd = useCallback(() => {
    setDraggingMarket(null);
    setDropTargetMarket(null);
    setDropTargetSide(null);
  }, []);

  const handleDragOver = useCallback(
    (market: MarketCode, side: MarketDropSide) => {
      if (!draggingMarket || draggingMarket === market) return;
      setDropTargetMarket(market);
      setDropTargetSide(side);
    },
    [draggingMarket],
  );

  const handleDrop = useCallback(
    (market: MarketCode, side: MarketDropSide) => {
      if (!draggingMarket) return;
      if (draggingMarket === market) {
        setDraggingMarket(null);
        setDropTargetMarket(null);
        setDropTargetSide(null);
        return;
      }
      setMarketOrder((prev) => {
        const next = reorderMarkets(prev, draggingMarket, market, side);
        storeMarketOrder(next);
        return next;
      });
      setDraggingMarket(null);
      setDropTargetMarket(null);
      setDropTargetSide(null);
    },
    [draggingMarket],
  );

  useEffect(() => {
    if (!crossMarketLink) {
      setCrossMarketLookup({});
      return;
    }

    setCrossMarketLookup({ us: undefined, cn: undefined, hk: undefined });
    let cancelled = false;

    fetchCrossMarketSectors(crossMarketLink.linkKey, {
      days: sectorFilters.days,
    }).then((markets) => {
      if (!cancelled) setCrossMarketLookup(markets);
    });

    return () => {
      cancelled = true;
    };
  }, [crossMarketLink, sectorFilters.days]);

  const handleSectorSelect = useCallback(
    (sector: SectorItem, market: MarketCode) => {
      const linkKey = sectorLinkKey(sector.concept_code);
      if (!linkKey) return;

      setCrossMarketLink((prev) => {
        if (
          prev?.sourceMarket === market &&
          prev.sourceConceptCode === sector.concept_code
        ) {
          return null;
        }
        return {
          linkKey,
          sourceMarket: market,
          sourceConceptCode: sector.concept_code,
          sourceName: sector.name,
          sourceChangePercent: sector.change_percent,
        };
      });
    },
    [],
  );

  const handleSectorJump = useCallback(
    (sector: SectorItem, market: MarketCode) => {
      const linkKey = sectorLinkKey(sector.concept_code);
      if (!linkKey) return;

      saveSectorJumpContext({
        concept_code: sector.concept_code,
        market,
        name_zh: sector.name.zh,
        name_en: sector.name.en,
        link_key: linkKey,
      });
      clearPersistedSectorViewState();
      onNavigateTab?.("sector");
    },
    [onNavigateTab],
  );

  const handleDynamicsSectorJump = useCallback(
    (impact: MarketDynamicsSectorImpact) => {
      const market = preferredImpactMarket(impact.affected_markets, marketOrder);
      const sector = dynamicsImpactToSectorItem(impact, market, taxonomy);
      if (!sector) return;
      handleSectorJump(sector, market);
    },
    [handleSectorJump, marketOrder, taxonomy],
  );

  const handleTickerClick = useCallback(
    (member: SectorMemberItem, market: MarketCode, sector: SectorItem) => {
      const linkKey = sectorLinkKey(sector.concept_code);
      const path =
        linkKey && taxonomy ? findSectorPathByLinkKey(taxonomy, linkKey) : null;
      openEntityTicker(onNavigateTab, {
        ticker: member.ticker,
        market,
        name_zh: member.name?.zh,
        name_en: member.name?.en,
        sector_source: path ? "navigation" : "search",
        sector_selection: path ? selectionFromPath(path) : undefined,
      });
    },
    [onNavigateTab, taxonomy],
  );

  if (loading && !data) {
    return (
      <section className="market-view market-view--loading" aria-busy="true">
        <LoadingIndicator
          className="market-view__status"
          label={t("marketPage.loading")}
          variant="page"
        />
      </section>
    );
  }

  if (error && !data) {
    return (
      <section className="market-view market-view--error">
        <p className="market-view__status">{t("marketPage.loadFailed")}</p>
        <button
          type="button"
          className="market-view__retry"
          onClick={reload}
        >
          {t("marketPage.retry")}
        </button>
      </section>
    );
  }

  if (!data) {
    return (
      <section className="market-view market-view--empty">
        <p className="market-view__status">{t("marketPage.noData")}</p>
      </section>
    );
  }

  const columnPanelProps = (
    code: MarketCode,
    flagSrc: string,
    label: string,
  ) => ({
    market: code,
    flagSrc,
    label,
    column: data.markets[code],
    sectorDays: sectorFilters.days,
    sectorsLoading,
    chartWindowStart: chartWindowsByMarket[code]?.start,
    chartWindowEnd: chartWindowsByMarket[code]?.end,
    crossMarketLink,
    lookupSector: crossMarketLookup[code],
    onSectorSelect: handleSectorSelect,
    onSectorJump: handleSectorJump,
    onTickerClick: handleTickerClick,
    linkedHoverDate: chartHoverDate,
    onLinkedHoverDateChange: setChartHoverDate,
  });

  const moversBarProps = {
    activeTab: sectorTab,
    onTabChange: setSectorTab,
    days: sectorFilters.days,
    minCapYi: sectorFilters.minCapYi,
    sectorLimit: sectorFilters.sectorLimit,
    eventCategory,
    discoveryDate,
    discoveryMinDate,
    discoveryMaxDate,
    loading:
      sectorTab === "discovery"
        ? discoveryLoading || dynamicsLoading
        : sectorsLoading,
    onDaysChange: (days: number) => updateSectorFilters({ days }),
    onMinCapYiChange: (minCapYi: number) => updateSectorFilters({ minCapYi }),
    onSectorLimitChange: (sectorLimit: number) =>
      updateSectorFilters({ sectorLimit }),
    onEventCategoryChange: setEventCategory,
    onDiscoveryDateChange: setDiscoveryDate,
  };

  const renderDiscoveryEventsPanel = () => (
    <section className="market-view__events" aria-label={t("marketPage.eventTimelineTitle")}>
      <MarketEventTimeline
        events={filteredEvents}
        marketOrder={marketOrder}
        selectionResetKey={`${discoveryDate}|${eventCategory}`}
        focusDate={discoveryDate || null}
        loading={dynamicsLoading}
        loadingMore={dynamicsLoadingMore}
        error={dynamicsError}
        hasMoreBefore={hasMoreBefore}
        hasMoreAfter={hasMoreAfter}
        onNearStart={loadMoreBefore}
        onNearEnd={loadMoreAfter}
        onRetry={reloadDynamics}
        onSectorJump={handleDynamicsSectorJump}
      />
    </section>
  );
  return (
    <section className="market-view" aria-label="Markets">
      <div className="market-view__layout">
        <div className="market-view__desktop-layout">
          {!isNarrowLayout ? (
            <div className="market-view__hero-row">
              {orderedColumns.map(({ code, flagSrc, label }) => (
                <DraggableMarketColumn
                  key={code}
                  market={code}
                  isDragging={draggingMarket === code}
                  dropSide={dropTargetMarket === code ? dropTargetSide : null}
                  onDragStart={handleDragStart}
                  onDragEnd={handleDragEnd}
                  onDragOver={handleDragOver}
                  onDrop={handleDrop}
                >
                  {(brandDrag) => (
                    <MarketColumnPanel
                      {...columnPanelProps(code, flagSrc, label)}
                      section="hero"
                      brandDrag={brandDrag}
                    />
                  )}
                </DraggableMarketColumn>
              ))}
              {!agentOpen && <AddMarketSlot />}
            </div>
          ) : null}

          <div className="market-view__toolbar-row">
            {!isNarrowLayout ? (
              <MarketSectorMoversBar {...moversBarProps} idPrefix="desktop" />
            ) : null}
            {!agentOpen ? (
              <div className="mesh-market-add-spacer" aria-hidden="true" />
            ) : null}
          </div>

          {sectorTab === "discovery" ? (
            <>
              <div className="market-view__events-row">
                {!isNarrowLayout ? renderDiscoveryEventsPanel() : null}
                {!agentOpen ? (
                  <div className="mesh-market-add-spacer" aria-hidden="true" />
                ) : null}
              </div>
              <div
                id="mesh-sector-panel-discovery-desktop"
                role="tabpanel"
                aria-labelledby="mesh-sector-tab-discovery-desktop"
                className="market-view__discovery-row"
              >
                {!isNarrowLayout
                  ? orderedColumns.map(({ code }) => (
                      <div
                        key={code}
                        className="mesh-market-column-wrap mesh-market-column-wrap--discovery"
                      >
                        <MarketSectorTreemap
                          market={code}
                          moves={discoveryMoves}
                          maxAbs={discoveryMaxAbs}
                          loading={discoveryLoading}
                          error={discoveryError}
                          onRetry={reloadDiscovery}
                          onSectorJump={handleSectorJump}
                        />
                      </div>
                    ))
                  : null}
                {!agentOpen ? (
                  <div className="mesh-market-add-spacer" aria-hidden="true" />
                ) : null}
              </div>
            </>
          ) : (
            <div
              id="mesh-sector-panel-movers-desktop"
              role="tabpanel"
              aria-labelledby="mesh-sector-tab-movers-desktop"
              className="market-view__sector-row"
            >
              {!isNarrowLayout
                ? orderedColumns.map(({ code, flagSrc, label }) => (
                    <div
                      key={code}
                      className="mesh-market-column-wrap mesh-market-column-wrap--sectors"
                    >
                      <MarketColumnPanel
                        {...columnPanelProps(code, flagSrc, label)}
                        section="sectors"
                      />
                    </div>
                  ))
                : null}
              {!agentOpen ? (
                <div className="mesh-market-add-spacer" aria-hidden="true" />
              ) : null}
            </div>
          )}
        </div>

        <div className="market-view__mobile-layout">
          {isNarrowLayout ? (
            <MarketSectorMoversBar {...moversBarProps} idPrefix="mobile" />
          ) : null}
          {sectorTab === "discovery" ? (
            <>
              <div className="market-view__events-row market-view__events-row--mobile">
                {isNarrowLayout ? renderDiscoveryEventsPanel() : null}
              </div>
              <div
                id="mesh-sector-panel-discovery-mobile"
                role="tabpanel"
                aria-labelledby="mesh-sector-tab-discovery-mobile"
                className="market-view__discovery-row market-view__discovery-row--mobile"
              >
                {isNarrowLayout
                  ? orderedColumns.map(({ code }) => (
                      <div
                        key={code}
                        className="mesh-market-column-wrap mesh-market-column-wrap--discovery"
                      >
                        <MarketSectorTreemap
                          market={code}
                          moves={discoveryMoves}
                          maxAbs={discoveryMaxAbs}
                          loading={discoveryLoading}
                          error={discoveryError}
                          onRetry={reloadDiscovery}
                          onSectorJump={handleSectorJump}
                        />
                      </div>
                    ))
                  : null}
              </div>
            </>
          ) : (
            isNarrowLayout
              ? orderedColumns.map(({ code, flagSrc, label }) => (
                  <div key={code} className="market-view__mobile-market">
                    <MarketColumnPanel
                      {...columnPanelProps(code, flagSrc, label)}
                      section="all"
                      chartIdSuffix="-mobile"
                    />
                  </div>
                ))
              : null
          )}
          {isNarrowLayout && !agentOpen ? <AddMarketSlot /> : null}
        </div>
      </div>
    </section>
  );
}
