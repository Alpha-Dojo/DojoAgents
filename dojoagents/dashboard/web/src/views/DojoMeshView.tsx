import { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchCrossMarketSectors, MARKET_COLUMNS } from '../api/dojoMesh';
import { AddMarketSlot } from '../components/DojoMesh/AddMarketSlot';
import { DraggableMarketColumn } from '../components/DojoMesh/DraggableMarketColumn';
import { useDojoMeshOverview } from '../hooks/useDojoMeshOverview';
import { useSectorTaxonomy } from '../hooks/useSectorTaxonomy';
import { useTranslation } from '../hooks/useTranslation';
import {
  readStoredMarketOrder,
  reorderMarkets,
  storeMarketOrder,
} from '../navigation/marketColumnOrder';
import { saveSphereSectorContext } from '../navigation/sphereContext';
import { openCoreTicker } from '../navigation/openCoreTicker';
import { clearPersistedSphereViewState } from '../cache/sphereViewState';
import { MarketColumnPanel } from '../components/DojoMesh/MarketColumnPanel';
import type { AppTab } from '../navigation/appTab';
import type { MarketCode, SectorItem, SectorMemberItem } from '../types/dojoMesh';
import type { CrossMarketLink, CrossMarketLookup } from '../utils/sectorLink';
import { sectorLinkKey } from '../utils/sectorLink';
import { findSectorPathByLinkKey, selectionFromPath } from '../utils/sectorTaxonomy';
import { resolveAlignedKlineYearWindowsFromBars } from '../utils/klineDate';
import './DojoMeshView.css';

interface DojoMeshViewProps {
  onNavigateTab?: (tab: AppTab) => void;
  agentOpen?: boolean;
}

export function DojoMeshView({ onNavigateTab, agentOpen = false }: DojoMeshViewProps) {
  const { t } = useTranslation();
  const { data, loading, error, reload } = useDojoMeshOverview(5);
  const { taxonomy } = useSectorTaxonomy();
  const [crossMarketLink, setCrossMarketLink] = useState<CrossMarketLink | null>(null);
  const [crossMarketLookup, setCrossMarketLookup] = useState<CrossMarketLookup>({});
  const [chartHoverDate, setChartHoverDate] = useState<string | null>(null);
  const [marketOrder, setMarketOrder] = useState<MarketCode[]>(readStoredMarketOrder);
  const [draggingMarket, setDraggingMarket] = useState<MarketCode | null>(null);
  const [dropTargetMarket, setDropTargetMarket] = useState<MarketCode | null>(null);

  const orderedColumns = useMemo(() => {
    const metaByCode = new Map(MARKET_COLUMNS.map((column) => [column.code, column]));
    return marketOrder
      .map((code) => metaByCode.get(code))
      .filter((column): column is (typeof MARKET_COLUMNS)[number] => column !== undefined);
  }, [marketOrder]);

  const chartWindowsByMarket = useMemo(() => {
    if (!data) return {} as Partial<Record<MarketCode, { start: string; end: string }>>;
    const barsByMarket: Partial<Record<MarketCode, { datetime: string }[]>> = {};
    for (const code of ['us', 'sh', 'hk'] as MarketCode[]) {
      const column = data.markets[code];
      if (!column) continue;
      barsByMarket[code] = column.benchmarks.flatMap((benchmark) => benchmark.kline);
    }
    return resolveAlignedKlineYearWindowsFromBars(barsByMarket) as Partial<
      Record<MarketCode, { start: string; end: string }>
    >;
  }, [data]);

  const handleDragStart = useCallback((market: MarketCode) => {
    setDraggingMarket(market);
    setDropTargetMarket(null);
  }, []);

  const handleDragEnd = useCallback(() => {
    setDraggingMarket(null);
    setDropTargetMarket(null);
  }, []);

  const handleDragOver = useCallback((market: MarketCode) => {
    if (!draggingMarket || draggingMarket === market) return;
    setDropTargetMarket(market);
  }, [draggingMarket]);

  const handleDrop = useCallback(
    (market: MarketCode) => {
      if (!draggingMarket) return;
      setMarketOrder((prev) => {
        const next = reorderMarkets(prev, draggingMarket, market);
        storeMarketOrder(next);
        return next;
      });
      setDraggingMarket(null);
      setDropTargetMarket(null);
    },
    [draggingMarket],
  );

  useEffect(() => {
    if (!crossMarketLink) {
      setCrossMarketLookup({});
      return;
    }

    setCrossMarketLookup({ us: undefined, sh: undefined, hk: undefined });
    let cancelled = false;

    fetchCrossMarketSectors(crossMarketLink.linkKey).then((markets) => {
      if (!cancelled) setCrossMarketLookup(markets);
    });

    return () => {
      cancelled = true;
    };
  }, [crossMarketLink]);

  const handleSectorSelect = useCallback((sector: SectorItem, market: MarketCode) => {
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
  }, []);

  const handleSectorJump = useCallback(
    (sector: SectorItem, market: MarketCode) => {
      console.log('Jumping to sector', sector.name, sector.concept_code, market);
      const linkKey = sectorLinkKey(sector.concept_code);
      console.log('Link key', linkKey);
      if (!linkKey) return;

      saveSphereSectorContext({
        concept_code: sector.concept_code,
        market,
        name_zh: sector.name.zh,
        name_en: sector.name.en,
        link_key: linkKey,
      });
      clearPersistedSphereViewState();
      onNavigateTab?.('sphere');
    },
    [onNavigateTab],
  );

  const handleTickerClick = useCallback(
    (member: SectorMemberItem, market: MarketCode, sector: SectorItem) => {
      const linkKey = sectorLinkKey(sector.concept_code);
      const path = linkKey && taxonomy ? findSectorPathByLinkKey(taxonomy, linkKey) : null;
      openCoreTicker(onNavigateTab, {
        ticker: member.ticker,
        market,
        name_zh: member.name?.zh,
        name_en: member.name?.en,
        sector_source: path ? 'navigation' : 'search',
        sector_selection: path ? selectionFromPath(path) : undefined,
      });
    },
    [onNavigateTab, taxonomy],
  );

  if (loading && !data) {
    return (
      <section className="dojo-mesh-view dojo-mesh-view--loading" aria-busy="true">
        <p className="dojo-mesh-view__status">{t('mesh.loading')}</p>
      </section>
    );
  }

  if (error && !data) {
    return (
      <section className="dojo-mesh-view dojo-mesh-view--error">
        <p className="dojo-mesh-view__status">{t('mesh.loadFailed')}</p>
        <button type="button" className="dojo-mesh-view__retry" onClick={reload}>
          {t('mesh.retry')}
        </button>
      </section>
    );
  }

  if (!data) {
    return (
      <section className="dojo-mesh-view dojo-mesh-view--empty">
        <p className="dojo-mesh-view__status">{t('mesh.noData')}</p>
      </section>
    );
  }

  return (
    <section className="dojo-mesh-view" aria-label="DojoMesh">
      <div className="dojo-mesh-view__grid">
        {orderedColumns.map(({ code, flag, label }) => (
          <DraggableMarketColumn
            key={code}
            market={code}
            isDragging={draggingMarket === code}
            isDropTarget={dropTargetMarket === code}
            onDragStart={handleDragStart}
            onDragEnd={handleDragEnd}
            onDragOver={handleDragOver}
            onDrop={handleDrop}
          >
            {(brandDrag) => (
              <MarketColumnPanel
                market={code}
                flag={flag}
                label={label}
                column={data.markets[code]}
                chartWindowStart={chartWindowsByMarket[code]?.start}
                chartWindowEnd={chartWindowsByMarket[code]?.end}
                crossMarketLink={crossMarketLink}
                lookupSector={crossMarketLookup[code]}
                onSectorSelect={handleSectorSelect}
                onSectorJump={handleSectorJump}
                onTickerClick={handleTickerClick}
                linkedHoverDate={chartHoverDate}
                onLinkedHoverDateChange={setChartHoverDate}
                brandDrag={brandDrag}
              />
            )}
          </DraggableMarketColumn>
        ))}
        {!agentOpen && <AddMarketSlot />}
      </div>
    </section>
  );
}
