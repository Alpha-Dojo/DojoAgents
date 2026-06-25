import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchCrossMarketSectors, MARKET_COLUMNS } from "../api/dojoMesh";
import { AddMarketSlot } from "../components/DojoMesh/AddMarketSlot";
import { DraggableMarketColumn } from "../components/DojoMesh/DraggableMarketColumn";
import { useDojoMeshOverview } from "../hooks/useDojoMeshOverview";
import { useSectorTaxonomy } from "../hooks/useSectorTaxonomy";
import { useTranslation } from "../hooks/useTranslation";
import {
  readStoredMarketOrder,
  reorderMarkets,
  storeMarketOrder,
  type MarketDropSide,
} from "../navigation/marketColumnOrder";
import { saveSphereSectorContext } from "../navigation/sphereContext";
import { openCoreTicker } from "../navigation/openCoreTicker";
import { clearPersistedSphereViewState } from "../cache/sphereViewState";
import { MeshSectorMoversBar } from "../components/DojoMesh/MeshSectorMoversBar";
import { MarketColumnPanel } from "../components/DojoMesh/MarketColumnPanel";
import type { AppTab } from "../navigation/appTab";
import type {
  MarketCode,
  SectorItem,
  SectorMemberItem,
} from "../types/dojoMesh";
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
} from "../utils/meshSectorFilters";
import "./DojoMeshView.css";

interface DojoMeshViewProps {
  onNavigateTab?: (tab: AppTab) => void;
  agentOpen?: boolean;
}

export function DojoMeshView({
  onNavigateTab,
  agentOpen = false,
}: DojoMeshViewProps) {
  const { t } = useTranslation();
  const [sectorFilters, setSectorFilters] = useState<MeshSectorFilterState>(
    readMeshSectorFilters,
  );
  const { data, loading, error, reload } = useDojoMeshOverview(sectorFilters);
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

      saveSphereSectorContext({
        concept_code: sector.concept_code,
        market,
        name_zh: sector.name.zh,
        name_en: sector.name.en,
        link_key: linkKey,
      });
      clearPersistedSphereViewState();
      onNavigateTab?.("sphere");
    },
    [onNavigateTab],
  );

  const handleTickerClick = useCallback(
    (member: SectorMemberItem, market: MarketCode, sector: SectorItem) => {
      const linkKey = sectorLinkKey(sector.concept_code);
      const path =
        linkKey && taxonomy ? findSectorPathByLinkKey(taxonomy, linkKey) : null;
      openCoreTicker(onNavigateTab, {
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
      <section
        className="dojo-mesh-view dojo-mesh-view--loading"
        aria-busy="true"
      >
        <p className="dojo-mesh-view__status">{t("mesh.loading")}</p>
      </section>
    );
  }

  if (error && !data) {
    return (
      <section className="dojo-mesh-view dojo-mesh-view--error">
        <p className="dojo-mesh-view__status">{t("mesh.loadFailed")}</p>
        <button
          type="button"
          className="dojo-mesh-view__retry"
          onClick={reload}
        >
          {t("mesh.retry")}
        </button>
      </section>
    );
  }

  if (!data) {
    return (
      <section className="dojo-mesh-view dojo-mesh-view--empty">
        <p className="dojo-mesh-view__status">{t("mesh.noData")}</p>
      </section>
    );
  }

  const columnPanelProps = (code: MarketCode, flagSrc: string, label: string) => ({
    market: code,
    flagSrc,
    label,
    column: data.markets[code],
    sectorDays: sectorFilters.days,
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

  return (
    <section className="dojo-mesh-view" aria-label="DojoMesh">
      <div className="dojo-mesh-view__layout">
        <div className="dojo-mesh-view__hero-row">
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

        <div className="dojo-mesh-view__toolbar-row">
          <MeshSectorMoversBar
            days={sectorFilters.days}
            minCapYi={sectorFilters.minCapYi}
            sectorLimit={sectorFilters.sectorLimit}
            loading={loading}
            onDaysChange={(days) => updateSectorFilters({ days })}
            onMinCapYiChange={(minCapYi) => updateSectorFilters({ minCapYi })}
            onSectorLimitChange={(sectorLimit) =>
              updateSectorFilters({ sectorLimit })
            }
          />
          {!agentOpen ? (
            <div className="mesh-market-add-spacer" aria-hidden="true" />
          ) : null}
        </div>

        <div className="dojo-mesh-view__sector-row">
          {orderedColumns.map(({ code, flagSrc, label }) => (
            <div
              key={code}
              className="mesh-market-column-wrap mesh-market-column-wrap--sectors"
            >
              <MarketColumnPanel
                {...columnPanelProps(code, flagSrc, label)}
                section="sectors"
              />
            </div>
          ))}
          {!agentOpen ? (
            <div className="mesh-market-add-spacer" aria-hidden="true" />
          ) : null}
        </div>
      </div>
    </section>
  );
}
