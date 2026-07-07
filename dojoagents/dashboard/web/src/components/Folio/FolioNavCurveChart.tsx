import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
  type ReactNode,
} from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import type { BenchmarkCatalogResponse } from '../../api/market';
import type { FolioOrder, FolioPerformanceView } from '../../types/folio';
import type { MarketCode } from '../../types/market';
import type { FolioNavWindowPreset } from '../../utils/folioNavWindow';
import { buildWindowRebasedByMarket, pickWindowMasterSeries } from '../../utils/folioNavWindow';
import { FolioNavWindowPresets } from './FolioNavWindowPresets';
import {
  buildRebasedBenchmarkSeriesBySymbol,
  type FolioBenchmarkHeadChip,
} from '../../utils/folioBenchmarkSeries';
import { formatSignedPercent, priceTickValues } from '../../utils/entityCharts';
import { formatStockPrice } from '../../utils/marketStats';
import { buildFolioOrderChartMarkers, type FolioOrderChartMarker } from '../../utils/folioOrderMarkers';
import { MARKET_CODE, MARKET_FLAG_IMAGE } from '../../utils/marketDisplay';
import { LoadingIndicator } from '../ui/LoadingIndicator';
import {
  PERFORMANCE_MARKET_CLASS,
  PERFORMANCE_MARKETS,
  buildHoverSnapshotForDate,
  buildIndependentMarketPath,
  buildLatestCumulativeSnapshot,
  buildCumulativeSnapshotForDate,
  buildMixedAxisEndLabel,
  alignMarketSeriesToMasterDates,
  clampViewRange,
  findVisibleIndexForDate,
  formatPerformanceReturnPercent,
  indexToChartX,
  latestMarketDates,
  pickMasterMarketSeries,
  rebaseMarketSeries,
  sliceMarketSeriesByDateRange,
  toMarketSeriesPoints,
  valueToChartY,
  type MarketSeriesPoint,
  type PerformanceHeadSnapshot,
} from '../../utils/sectorPerformanceSeries';
import { resolveFolioChartSeriesByMarket } from '../../utils/folioNavSeries';

const MARKETS = PERFORMANCE_MARKETS;
const CHART_W = 640;
const CHART_H = 140;
const PAD_X = 6;
const PAD_Y = 6;
const MIN_VISIBLE_POINTS = 5;
const FULL_VIEW = { start: 0, end: 1 };

interface ViewRange {
  start: number;
  end: number;
}

interface FolioChartGeometry {
  yMin: number;
  yMax: number;
  masterMarket: MarketCode;
  benchmarkPaths: Array<{ symbol: string; path: string }>;
  layers: Array<{ market: MarketCode; portfolioPath: string }>;
}

function collectBenchmarkValues(
  performance: FolioPerformanceView,
  visibleDates: string[],
  benchmarkSymbols: string[],
  catalog: BenchmarkCatalogResponse | null,
): number[] {
  const values: number[] = [];
  const rebasedBySymbol = buildRebasedBenchmarkSeriesBySymbol(
    benchmarkSymbols,
    catalog,
    visibleDates,
    performance,
  );

  for (const symbol of benchmarkSymbols) {
    const series = rebasedBySymbol[symbol];
    if (series?.length) {
      values.push(...series.map((point) => point.value));
      continue;
    }
    if (symbol !== benchmarkSymbols[0]) continue;
    const fallback = pickBenchmarkSeries(performance, symbol);
    if (fallback.length >= 2) {
      const aligned = alignMarketSeriesToMasterDates(
        visibleDates,
        normalizeSeries(fallback),
      );
      const rebased = rebaseMarketSeries(aligned);
      values.push(...rebased.map((point) => point.value));
    }
  }

  return values;
}

function buildBenchmarkPaths(
  performance: FolioPerformanceView,
  visibleDates: string[],
  benchmarkSymbols: string[],
  catalog: BenchmarkCatalogResponse | null,
  yMin: number,
  yMax: number,
): Array<{ symbol: string; path: string }> {
  const rebasedBySymbol = buildRebasedBenchmarkSeriesBySymbol(
    benchmarkSymbols,
    catalog,
    visibleDates,
    performance,
  );

  return benchmarkSymbols.flatMap((symbol) => {
    const rebased =
      rebasedBySymbol[symbol] ??
      (symbol === benchmarkSymbols[0]
        ? (() => {
            const fallback = pickBenchmarkSeries(performance, symbol);
            if (fallback.length < 2) return null;
            const aligned = alignMarketSeriesToMasterDates(visibleDates, normalizeSeries(fallback));
            const rebased = rebaseMarketSeries(aligned);
            return rebased.length >= 2 ? rebased : null;
          })()
        : null);

    if (!rebased || rebased.length < 2) return [];
    return [
      {
        symbol,
        path: buildIndependentMarketPath(
          rebased,
          CHART_W,
          CHART_H,
          yMin,
          yMax,
          PAD_X,
          PAD_Y,
        ),
      },
    ];
  });
}

function buildFolioVisibleChart(
  performance: FolioPerformanceView,
  visibleByMarket: Partial<Record<MarketCode, MarketSeriesPoint[]>>,
  visibleDates: string[],
  benchmarkSymbols: string[],
  benchmarkCatalog: BenchmarkCatalogResponse | null,
  markets: MarketCode[] = MARKETS,
): FolioChartGeometry | null {
  const layers = markets.map((market) => {
    const source = visibleByMarket[market];
    if (!source || source.length < 2) return null;
    const points = alignMarketSeriesToMasterDates(visibleDates, source);
    if (points.length < 2) return null;
    return { market, points };
  }).filter(Boolean) as Array<{ market: MarketCode; points: MarketSeriesPoint[] }>;

  if (layers.length === 0 || visibleDates.length < 2) return null;

  const benchmarkValues = collectBenchmarkValues(
    performance,
    visibleDates,
    benchmarkSymbols,
    benchmarkCatalog,
  );

  const values = layers.flatMap((layer) => layer.points.map((point) => point.value));
  if (benchmarkValues.length) values.push(...benchmarkValues);

  const dataMin = Math.min(...values);
  const dataMax = Math.max(...values);
  const span = dataMax - dataMin || 1;
  const pad = Math.max(span * 0.08, 1.5);
  const yMin = dataMin - pad;
  const yMax = dataMax + pad;

  const masterMarket =
    layers.reduce((best, layer) =>
      layer.points.length > best.points.length ? layer : best,
    ).market;

  return {
    yMin,
    yMax,
    masterMarket,
    benchmarkPaths: buildBenchmarkPaths(
      performance,
      visibleDates,
      benchmarkSymbols,
      benchmarkCatalog,
      yMin,
      yMax,
    ),
    layers: layers.map((layer) => ({
      market: layer.market,
      portfolioPath: buildIndependentMarketPath(
        layer.points,
        CHART_W,
        CHART_H,
        yMin,
        yMax,
        PAD_X,
        PAD_Y,
      ),
    })),
  };
}

function buildReturnAxisTicks(
  yMin: number,
  yMax: number,
  count = 5,
): Array<{ indexValue: number; label: string; y: number; topPct: number }> {
  const pctMin = yMin - 100;
  const pctMax = yMax - 100;
  const span = Math.abs(pctMax - pctMin);
  const digits = span <= 15 ? 1 : 0;

  return priceTickValues(pctMin, pctMax, count).map((pct) => {
    const indexValue = pct + 100;
    const y = valueToChartY(indexValue, yMin, yMax, CHART_H, PAD_Y);
    return {
      indexValue,
      label: formatSignedPercent(pct, digits),
      y,
      topPct: (y / CHART_H) * 100,
    };
  });
}

interface FolioNavCurveChartProps {
  performance: FolioPerformanceView | null | undefined;
  orders?: FolioOrder[];
  loading?: boolean;
  benchmarkSymbols?: string[];
  benchmarkCatalog?: BenchmarkCatalogResponse | null;
  visibleMarkets?: MarketCode[];
  hoverDate?: string | null;
  onHoverDateChange?: (date: string | null) => void;
  windowRebasedByMarket: Partial<Record<MarketCode, MarketSeriesPoint[]>>;
}

function normalizeSeries(
  points: Array<{ date: string; value: number }> | undefined,
): Array<{ date: string; value: number }> {
  if (!points?.length) return [];
  return points
    .map((point) => ({
      date: point.date,
      value: Number(point.value),
    }))
    .filter((point) => point.date && Number.isFinite(point.value));
}

function alignSeriesToDates(
  dates: string[],
  source: Array<{ date: string; value: number }>,
  fallback: number[],
): number[] {
  const byDate = new Map(source.map((point) => [point.date, Number(point.value)]));
  return dates.map((date, index) => {
    const matched = byDate.get(date);
    return matched != null && Number.isFinite(matched) ? matched : fallback[index] ?? 100;
  });
}

function pickBenchmarkSeries(
  performance: FolioPerformanceView,
  benchmarkSymbol?: string | null,
): Array<{ date: string; value: number }> {
  if (benchmarkSymbol) {
    for (const market of MARKETS) {
      const symbol = performance.benchmarkSymbolByMarket[market];
      const series = performance.benchmarkByMarket[market];
      if (symbol === benchmarkSymbol && series?.length) {
        return normalizeSeries(series);
      }
    }
  }

  for (const market of MARKETS) {
    const series = performance.benchmarkByMarket[market];
    if (series?.length) {
      return normalizeSeries(series);
    }
  }
  return [];
}

export function useFolioNavCurveModel(
  performance: FolioPerformanceView | null | undefined,
  benchmarkSymbol?: string | null,
  markets: MarketCode[] = MARKETS,
) {
  const rebasedByMarket = useMemo(() => {
    if (!performance) return {} as Partial<Record<MarketCode, MarketSeriesPoint[]>>;
    const chartSeries = resolveFolioChartSeriesByMarket(performance);
    const result: Partial<Record<MarketCode, MarketSeriesPoint[]>> = {};
    for (const market of markets) {
      const raw = toMarketSeriesPoints(chartSeries[market]);
      if (raw.length >= 2) {
        result[market] = rebaseMarketSeries(raw);
      }
    }
    return result;
  }, [markets, performance]);

  const master = useMemo(
    () => pickMasterMarketSeries(rebasedByMarket, markets),
    [markets, rebasedByMarket],
  );

  const chart = useMemo(() => {
    if (!performance) return null;

    const layers = markets.map((market) => {
      const portfolioPoints = rebasedByMarket[market];
      if (!portfolioPoints || portfolioPoints.length < 2) return null;

      return {
        market,
        dates: portfolioPoints.map((point) => point.date),
        portfolio: portfolioPoints.map((point) => point.value),
      };
    }).filter(Boolean) as Array<{
      market: MarketCode;
      dates: string[];
      portfolio: number[];
    }>;

    if (layers.length === 0) return null;

    const masterLayer = layers.reduce((best, layer) =>
      layer.dates.length > best.dates.length ? layer : best,
    );

    const benchmarkSource = pickBenchmarkSeries(performance, benchmarkSymbol);
    const benchmarkValues =
      benchmarkSource.length >= 2
        ? alignSeriesToDates(
            masterLayer.dates,
            benchmarkSource,
            masterLayer.dates.map(() => 100),
          )
        : null;

    const values = layers.flatMap((layer) => layer.portfolio);
    if (benchmarkValues) values.push(...benchmarkValues);

    const dataMin = Math.min(...values);
    const dataMax = Math.max(...values);
    const span = dataMax - dataMin || 1;
    const pad = Math.max(span * 0.08, 1.5);
    const yMin = dataMin - pad;
    const yMax = dataMax + pad;

    return {
      yMin,
      yMax,
      dates: masterLayer.dates,
      masterMarket: masterLayer.market,
      benchmarkPath:
        benchmarkValues && benchmarkValues.length >= 2
          ? buildIndependentMarketPath(
              benchmarkValues.map((value, index) => ({
                date: masterLayer.dates[index] ?? '',
                value,
              })),
              CHART_W,
              CHART_H,
              yMin,
              yMax,
              PAD_X,
              PAD_Y,
            )
          : '',
      layers: layers.map((layer) => ({
        market: layer.market,
        portfolioPath: buildIndependentMarketPath(
          layer.portfolio.map((value, index) => ({
            date: layer.dates[index] ?? '',
            value,
          })),
          CHART_W,
          CHART_H,
          yMin,
          yMax,
          PAD_X,
          PAD_Y,
        ),
      })),
    };
  }, [benchmarkSymbol, markets, performance, rebasedByMarket]);

  const defaultSnapshot = useMemo(
    () => buildLatestCumulativeSnapshot(rebasedByMarket, markets),
    [markets, rebasedByMarket],
  );

  return { rebasedByMarket, master, chart, defaultSnapshot };
}

export function buildFolioNavDisplaySnapshot(
  hoverDate: string | null | undefined,
  rebasedByMarket: Partial<Record<MarketCode, MarketSeriesPoint[]>>,
  defaultSnapshot: PerformanceHeadSnapshot | null,
  markets: MarketCode[] = MARKETS,
): PerformanceHeadSnapshot | null {
  if (hoverDate) {
    return buildCumulativeSnapshotForDate(hoverDate, rebasedByMarket, markets);
  }
  return defaultSnapshot;
}

interface FolioNavCurveMarketHeadProps {
  snapshot: PerformanceHeadSnapshot | null;
  loading?: boolean;
  visibleMarkets?: MarketCode[];
}

export function FolioNavCurveMarketHead({
  snapshot,
  loading = false,
  visibleMarkets = MARKETS,
}: FolioNavCurveMarketHeadProps) {
  const { t } = useTranslation();

  if (loading) {
    return <span className="folio-performance__head-placeholder">{t('folio.loading')}</span>;
  }

  if (!snapshot?.markets.length) {
    return null;
  }

  return (
    <div className="folio-performance__inline-markets">
      {visibleMarkets.flatMap((market) => {
        const chip = snapshot.markets.find((item) => item.market === market);
        if (!chip) return [];
        return [
          <span
            key={market}
            className={`folio-performance__inline-market folio-performance__inline-market--${PERFORMANCE_MARKET_CLASS[market]}`}
          >
            <img className="folio-performance__inline-flag" src={MARKET_FLAG_IMAGE[market]} alt="" aria-hidden />
            <span className="folio-performance__inline-code">{MARKET_CODE[market]}</span>
            <span
              className={`folio-performance__inline-return folio-performance__inline-return--${
                chip.value >= 100 ? 'up' : 'down'
              }`}
            >
              {formatPerformanceReturnPercent(chip.value)}
            </span>
          </span>,
        ];
      })}
    </div>
  );
}

interface FolioNavCurveBenchmarkHeadProps {
  chips: FolioBenchmarkHeadChip[];
  loading?: boolean;
}

export function FolioNavCurveBenchmarkHead({
  chips,
  loading = false,
}: FolioNavCurveBenchmarkHeadProps) {
  if (loading || chips.length === 0) {
    return null;
  }

  return (
    <div className="folio-performance__inline-benchmarks">
      {chips.map((chip) => (
        <span
          key={chip.symbol}
          className={`folio-performance__inline-benchmark folio-performance__inline-benchmark--${PERFORMANCE_MARKET_CLASS[chip.market]}`}
          title={chip.label}
        >
          <img className="folio-performance__inline-flag" src={MARKET_FLAG_IMAGE[chip.market]} alt="" aria-hidden />
          <span className="folio-performance__inline-benchmark-label">{chip.label}</span>
          <span
            className={`folio-performance__inline-return folio-performance__inline-return--${
              chip.value >= 100 ? 'up' : 'down'
            }`}
          >
            {formatPerformanceReturnPercent(chip.value)}
          </span>
        </span>
      ))}
    </div>
  );
}

export function FolioNavCurveChart({
  performance,
  orders = [],
  loading = false,
  benchmarkSymbols = [],
  benchmarkCatalog = null,
  visibleMarkets = MARKETS,
  hoverDate = null,
  onHoverDateChange,
  windowRebasedByMarket,
}: FolioNavCurveChartProps) {
  const { t, locale } = useTranslation();
  const chartRef = useRef<HTMLDivElement>(null);
  const plotRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{ startX: number; view: ViewRange } | null>(null);
  const [internalHoverDate, setInternalHoverDate] = useState<string | null>(null);
  const [viewRange, setViewRange] = useState<ViewRange>(FULL_VIEW);
  const [isDragging, setIsDragging] = useState(false);
  const [hoveredOrderMarker, setHoveredOrderMarker] = useState<FolioOrderChartMarker | null>(null);
  const activeHoverDate = onHoverDateChange ? hoverDate : internalHoverDate;
  const setHoverDate = onHoverDateChange ?? setInternalHoverDate;

  const master = useMemo(
    () => pickWindowMasterSeries(windowRebasedByMarket, visibleMarkets),
    [visibleMarkets, windowRebasedByMarket],
  );

  const masterKey = master?.series.map((point) => point.date).join('|') ?? '';
  const benchmarkKey = benchmarkSymbols.join('|');

  useEffect(() => {
    setViewRange(FULL_VIEW);
  }, [masterKey, benchmarkKey]);

  const minViewSpan = useMemo(() => {
    const total = master?.series.length ?? 0;
    if (total <= 1) return 1;
    return Math.min(1, Math.max(MIN_VISIBLE_POINTS / total, 0.06));
  }, [master?.series.length]);

  const visibleWindow = useMemo(() => {
    const series = master?.series ?? [];
    if (series.length < 2) {
      return {
        series,
        startDate: series[0]?.date ?? '',
        endDate: series[series.length - 1]?.date ?? '',
      };
    }

    const lastIndex = series.length - 1;
    const startIndex = Math.floor(viewRange.start * lastIndex);
    const endIndex = Math.ceil(viewRange.end * lastIndex);
    const visible = series.slice(startIndex, endIndex + 1);

    return {
      series: visible.length >= 2 ? visible : series,
      startDate: visible[0]?.date ?? series[0].date,
      endDate: visible[visible.length - 1]?.date ?? series[lastIndex].date,
    };
  }, [master, viewRange]);

  const visibleByMarket = useMemo(() => {
    const { startDate, endDate } = visibleWindow;
    if (!startDate || !endDate || !performance) {
      return {} as Partial<Record<MarketCode, MarketSeriesPoint[]>>;
    }

    const result: Partial<Record<MarketCode, MarketSeriesPoint[]>> = {};
    for (const market of visibleMarkets) {
      const sliced = sliceMarketSeriesByDateRange(windowRebasedByMarket[market] ?? [], startDate, endDate);
      if (sliced.length >= 2) {
        result[market] = sliced;
      }
    }
    return result;
  }, [performance, visibleMarkets, visibleWindow, windowRebasedByMarket]);

  const chart = useMemo(() => {
    if (!performance) return null;
    return buildFolioVisibleChart(
      performance,
      visibleByMarket,
      visibleWindow.series.map((point) => point.date),
      benchmarkSymbols,
      benchmarkCatalog,
      visibleMarkets,
    );
  }, [benchmarkCatalog, benchmarkSymbols, performance, visibleByMarket, visibleMarkets, visibleWindow.series]);

  const yAxisTicks = useMemo(
    () => (chart ? buildReturnAxisTicks(chart.yMin, chart.yMax) : []),
    [chart],
  );

  const orderMarkers = useMemo(() => {
    if (!chart || !orders.length) return [];
    return buildFolioOrderChartMarkers(
      orders.filter((order) => visibleMarkets.includes(order.market)),
      visibleWindow.series,
      windowRebasedByMarket,
      CHART_W,
      CHART_H,
      PAD_X,
      PAD_Y,
    );
  }, [chart, orders, visibleMarkets, windowRebasedByMarket, visibleWindow.series]);

  const axisEndLabel = useMemo(
    () => buildMixedAxisEndLabel(latestMarketDates(windowRebasedByMarket)),
    [windowRebasedByMarket],
  );

  const displayGeometry = useMemo(() => {
    if (isDragging || !activeHoverDate || !chart) return null;

    const localIndex = findVisibleIndexForDate(visibleWindow.series, activeHoverDate);
    if (localIndex == null) return null;

    const count = visibleWindow.series.length;
    const x = indexToChartX(localIndex, count, CHART_W, PAD_X);
    const anchorSnapshot = buildHoverSnapshotForDate(activeHoverDate, windowRebasedByMarket, visibleMarkets);
    if (!anchorSnapshot) return null;

    const dots = visibleMarkets.map((market) => {
      const value = anchorSnapshot.values[market];
      if (value == null) return null;
      return {
        market,
        x,
        y: valueToChartY(value, chart.yMin, chart.yMax, CHART_H, PAD_Y),
      };
    }).filter((item): item is { market: MarketCode; x: number; y: number } => item != null);

    const masterValue = anchorSnapshot.values[chart.masterMarket];
    const crosshairY =
      masterValue != null
        ? valueToChartY(masterValue, chart.yMin, chart.yMax, CHART_H, PAD_Y)
        : null;

    return { x, y: crosshairY, dots };
  }, [activeHoverDate, chart, isDragging, visibleMarkets, windowRebasedByMarket, visibleWindow.series]);

  const updateHoverFromClientX = useCallback(
    (clientX: number) => {
      if (!plotRef.current || !visibleWindow.series.length || isDragging) return;
      const rect = plotRef.current.getBoundingClientRect();
      const ratio = Math.min(Math.max((clientX - rect.left) / rect.width, 0), 1);
      const index = Math.round(ratio * Math.max(visibleWindow.series.length - 1, 0));
      const anchor = visibleWindow.series[index];
      if (anchor) setHoverDate(anchor.date);
    },
    [isDragging, setHoverDate, visibleWindow.series],
  );

  const endDrag = useCallback(() => {
    dragRef.current = null;
    setIsDragging(false);
  }, []);

  const handleMouseDown = useCallback(
    (event: ReactMouseEvent<HTMLDivElement>) => {
      if (event.button !== 0 || !master?.series.length) return;
      event.preventDefault();
      event.stopPropagation();
      dragRef.current = { startX: event.clientX, view: viewRange };
      setIsDragging(true);
      setHoverDate(null);
      setHoveredOrderMarker(null);
    },
    [master?.series.length, setHoverDate, viewRange],
  );

  const handleMouseMove = useCallback(
    (event: ReactMouseEvent<HTMLDivElement>) => {
      if (dragRef.current) {
        const rect = plotRef.current?.getBoundingClientRect();
        if (!rect) return;
        const dx = event.clientX - dragRef.current.startX;
        const span = dragRef.current.view.end - dragRef.current.view.start;
        const shift = -(dx / rect.width) * span;
        setViewRange(
          clampViewRange(
            dragRef.current.view.start + shift,
            dragRef.current.view.end + shift,
            minViewSpan,
          ),
        );
        return;
      }
      updateHoverFromClientX(event.clientX);
    },
    [minViewSpan, updateHoverFromClientX],
  );

  useEffect(() => {
    if (!isDragging) return;

    const handleWindowMouseUp = () => endDrag();
    const handleWindowMouseMove = (event: MouseEvent) => {
      if (!dragRef.current || !plotRef.current) return;
      const rect = plotRef.current.getBoundingClientRect();
      const dx = event.clientX - dragRef.current.startX;
      const span = dragRef.current.view.end - dragRef.current.view.start;
      const shift = -(dx / rect.width) * span;
      setViewRange(
        clampViewRange(
          dragRef.current.view.start + shift,
          dragRef.current.view.end + shift,
          minViewSpan,
        ),
      );
    };

    window.addEventListener('mouseup', handleWindowMouseUp);
    window.addEventListener('mousemove', handleWindowMouseMove);
    return () => {
      window.removeEventListener('mouseup', handleWindowMouseUp);
      window.removeEventListener('mousemove', handleWindowMouseMove);
    };
  }, [endDrag, isDragging, minViewSpan]);

  useEffect(() => {
    const el = chartRef.current;
    if (!el || !master?.series.length) return;

    const handleWheel = (event: WheelEvent) => {
      event.preventDefault();
      event.stopPropagation();

      const rect = plotRef.current?.getBoundingClientRect() ?? el.getBoundingClientRect();
      const ratio = Math.min(Math.max((event.clientX - rect.left) / rect.width, 0), 1);
      const zoomFactor = event.deltaY > 0 ? 1.12 : 0.88;

      setViewRange((current) => {
        const span = current.end - current.start;
        const nextSpan = Math.min(1, Math.max(minViewSpan, span * zoomFactor));
        const anchor = current.start + ratio * span;
        return clampViewRange(anchor - ratio * nextSpan, anchor + (1 - ratio) * nextSpan, minViewSpan);
      });
    };

    el.addEventListener('wheel', handleWheel, { passive: false });
    return () => el.removeEventListener('wheel', handleWheel);
  }, [master?.series.length, minViewSpan]);

  const handleMarkerEnter = useCallback(
    (marker: FolioOrderChartMarker) => {
      setHoveredOrderMarker(marker);
      setHoverDate(marker.date);
    },
    [setHoverDate],
  );

  const handleMarkerLeave = useCallback((markerId: string) => {
    setHoveredOrderMarker((current) => (current?.id === markerId ? null : current));
  }, []);

  const handleMouseLeave = useCallback(() => {
    endDrag();
    setHoverDate(null);
    setHoveredOrderMarker(null);
  }, [endDrag, setHoverDate]);

  if (!chart) {
    if (loading) {
      return (
        <LoadingIndicator
          className="folio-performance__empty"
          label={t('folio.loading')}
          variant="panel"
        />
      );
    }

    return (
      <p className="folio-performance__empty">{t('folio.noPerformanceData')}</p>
    );
  }

  const baselineY =
    chart.yMax > chart.yMin
      ? PAD_Y + (CHART_H - PAD_Y * 2) * (1 - (100 - chart.yMin) / (chart.yMax - chart.yMin))
      : CHART_H / 2;

  const startDate = visibleWindow.startDate || master?.series[0]?.date || '';

  return (
    <>
      <div
        ref={chartRef}
        className={`folio-performance__chart-stage${
          isDragging ? ' folio-performance__chart-stage--dragging' : ''
        }`}
        onMouseMove={handleMouseMove}
        onMouseDown={handleMouseDown}
        onMouseUp={endDrag}
        onMouseLeave={handleMouseLeave}
      >
        <div className="folio-performance__return-axis" aria-hidden>
          {yAxisTicks.map((tick) => (
            <span
              key={tick.indexValue}
              className="folio-performance__return-tick"
              style={{ top: `${tick.topPct}%` }}
            >
              {tick.label}
            </span>
          ))}
        </div>
        <div ref={plotRef} className="folio-performance__chart-body">
          {orderMarkers.length > 0 ? (
            <div className="folio-performance__order-legend" aria-hidden>
              <span className="folio-performance__order-legend-item folio-performance__order-legend-item--buy">
                {t('folio.orderBuy')}
              </span>
              <span className="folio-performance__order-legend-item folio-performance__order-legend-item--sell">
                {t('folio.orderSell')}
              </span>
            </div>
          ) : null}
          {hoveredOrderMarker ? (
            <div
              className={`folio-performance__order-tooltip${
                hoveredOrderMarker.side === 'sell'
                  ? ' folio-performance__order-tooltip--below'
                  : ''
              }`}
              style={{
                left: `${(hoveredOrderMarker.x / CHART_W) * 100}%`,
                top: `${(hoveredOrderMarker.y / CHART_H) * 100}%`,
              }}
              role="tooltip"
            >
              <div className="folio-performance__order-tooltip-head">
                <span className="folio-performance__order-tooltip-ticker">{hoveredOrderMarker.ticker}</span>
                <span className="folio-performance__order-tooltip-name">
                  {locale === 'zh' && hoveredOrderMarker.nameZh
                    ? hoveredOrderMarker.nameZh
                    : hoveredOrderMarker.nameEn || hoveredOrderMarker.name}
                </span>
              </div>
              <div className="folio-performance__order-tooltip-row">
                <span
                  className={`folio-performance__order-tooltip-side folio-performance__order-tooltip-side--${hoveredOrderMarker.side}`}
                >
                  {hoveredOrderMarker.side === 'buy' ? t('folio.orderBuy') : t('folio.orderSell')}
                </span>
                <span className="folio-performance__order-tooltip-sep" aria-hidden>
                  ·
                </span>
                <span>
                  {t('folio.orderQty')} {hoveredOrderMarker.qty}
                </span>
              </div>
              <div className="folio-performance__order-tooltip-row">
                <span>
                  {(hoveredOrderMarker.fillTime ?? hoveredOrderMarker.orderTime ?? hoveredOrderMarker.date).slice(0, 10)}
                </span>
                <span className="folio-performance__order-tooltip-sep" aria-hidden>
                  ·
                </span>
                <span>
                  {t('folio.orderTooltipFillPrice')}{' '}
                  {formatStockPrice(hoveredOrderMarker.fillPrice ?? hoveredOrderMarker.price)}
                </span>
              </div>
            </div>
          ) : null}
          <svg
            className="folio-performance__chart"
            width="100%"
            height={CHART_H}
            viewBox={`0 0 ${CHART_W} ${CHART_H}`}
            preserveAspectRatio="none"
            aria-hidden
          >
            {yAxisTicks.map((tick) => (
              <line
                key={`grid-${tick.indexValue}`}
                x1={PAD_X}
                y1={tick.y}
                x2={CHART_W - PAD_X}
                y2={tick.y}
                className="folio-performance__grid"
              />
            ))}
            <line
              x1={PAD_X}
              y1={baselineY}
              x2={CHART_W - PAD_X}
              y2={baselineY}
              className="folio-performance__baseline"
            />
            {chart.benchmarkPaths.map((layer) => (
              <path
                key={layer.symbol}
                d={layer.path}
                className="folio-performance__line folio-performance__line--benchmark"
              />
            ))}
            {chart.layers.map((layer) => (
              <path
                key={layer.market}
                d={layer.portfolioPath}
                className={`folio-performance__line folio-performance__line--${PERFORMANCE_MARKET_CLASS[layer.market]}`}
              />
            ))}
            {orderMarkers.length > 0 ? (
              <g className="folio-performance__order-markers" aria-hidden={false}>
                {orderMarkers.map((marker) => {
                  const isBuy = marker.side === 'buy';
                  const points = isBuy
                    ? `${marker.x},${marker.y - 6} ${marker.x - 4.5},${marker.y + 2} ${marker.x + 4.5},${marker.y + 2}`
                    : `${marker.x},${marker.y + 6} ${marker.x - 4.5},${marker.y - 2} ${marker.x + 4.5},${marker.y - 2}`;
                  return (
                    <g key={marker.id}>
                      <circle
                        cx={marker.x}
                        cy={marker.y}
                        r={12}
                        className="folio-performance__order-marker-hit"
                        onMouseEnter={(event) => {
                          event.stopPropagation();
                          handleMarkerEnter(marker);
                        }}
                        onMouseLeave={(event) => {
                          event.stopPropagation();
                          handleMarkerLeave(marker.id);
                        }}
                      />
                      <polygon
                        points={points}
                        className={`folio-performance__order-marker folio-performance__order-marker--${marker.side}${
                          hoveredOrderMarker?.id === marker.id
                            ? ' folio-performance__order-marker--active'
                            : ''
                        }`}
                        pointerEvents="none"
                      />
                    </g>
                  );
                })}
              </g>
            ) : null}
            {displayGeometry ? (
              <g className="folio-performance__crosshair">
                <line
                  x1={displayGeometry.x}
                  y1={PAD_Y}
                  x2={displayGeometry.x}
                  y2={CHART_H - PAD_Y}
                  className="folio-performance__crosshair-v"
                />
                {displayGeometry.y != null ? (
                  <line
                    x1={PAD_X}
                    y1={displayGeometry.y}
                    x2={CHART_W - PAD_X}
                    y2={displayGeometry.y}
                    className="folio-performance__crosshair-h"
                  />
                ) : null}
                {displayGeometry.dots.map((dot) => (
                  <circle
                    key={dot.market}
                    cx={dot.x}
                    cy={dot.y}
                    r={3.2}
                    className={`folio-performance__hover-dot folio-performance__hover-dot--${PERFORMANCE_MARKET_CLASS[dot.market]}`}
                  />
                ))}
              </g>
            ) : null}
          </svg>
        </div>
      </div>
      <div className="folio-performance__axis" aria-hidden>
        <span className="folio-performance__axis-tick folio-performance__axis-tick--start">
          {startDate}
        </span>
        <span
          className={`folio-performance__axis-tick folio-performance__axis-tick--active${
            activeHoverDate && !isDragging ? ' folio-performance__axis-tick--visible' : ''
          }`}
        >
          {activeHoverDate ?? ''}
        </span>
        <span className="folio-performance__axis-tick folio-performance__axis-tick--end">
          {axisEndLabel}
        </span>
      </div>
    </>
  );
}

export interface FolioNavCurveHeadContext {
  hoverDate: string | null;
  anchorDate: string | null;
  windowPreset: FolioNavWindowPreset;
  windowRebasedByMarket: Partial<Record<MarketCode, MarketSeriesPoint[]>>;
}

interface FolioNavCurveSectionProps {
  performance: FolioPerformanceView | null | undefined;
  orders?: FolioOrder[];
  loading?: boolean;
  benchmarkSymbols?: string[];
  benchmarkCatalog?: BenchmarkCatalogResponse | null;
  visibleMarkets?: MarketCode[];
  benchmarkControl?: (context: FolioNavCurveHeadContext) => ReactNode;
}

export function FolioNavCurveSection({
  performance,
  orders = [],
  loading = false,
  benchmarkSymbols = [],
  benchmarkCatalog = null,
  visibleMarkets,
  benchmarkControl,
}: FolioNavCurveSectionProps) {
  const { t } = useTranslation();
  const [hoverDate, setHoverDate] = useState<string | null>(null);
  const [windowPreset, setWindowPreset] = useState<FolioNavWindowPreset>('all');
  const activeMarkets = visibleMarkets?.length ? visibleMarkets : MARKETS;
  const { rebasedByMarket } = useFolioNavCurveModel(
    performance,
    benchmarkSymbols[0] ?? null,
    activeMarkets,
  );

  const windowRebasedByMarket = useMemo(
    () => buildWindowRebasedByMarket(rebasedByMarket, windowPreset, activeMarkets),
    [activeMarkets, rebasedByMarket, windowPreset],
  );

  const windowDefaultSnapshot = useMemo(
    () => buildLatestCumulativeSnapshot(windowRebasedByMarket, activeMarkets),
    [activeMarkets, windowRebasedByMarket],
  );

  const displaySnapshot = buildFolioNavDisplaySnapshot(
    hoverDate,
    windowRebasedByMarket,
    windowDefaultSnapshot,
    activeMarkets,
  );

  const handleWindowPresetChange = useCallback((preset: FolioNavWindowPreset) => {
    setWindowPreset(preset);
    setHoverDate(null);
  }, []);

  const headContext: FolioNavCurveHeadContext = {
    hoverDate,
    anchorDate: displaySnapshot?.anchorDate ?? null,
    windowPreset,
    windowRebasedByMarket,
  };

  return (
    <>
      <header className="folio-card__head folio-performance__head">
        <div className="folio-performance__head-leading">
          <h3 className="folio-card__title">{t('folio.navCurve')}</h3>
          <FolioNavWindowPresets value={windowPreset} onChange={handleWindowPresetChange} />
        </div>
        <div className="folio-performance__head-tail">
          <FolioNavCurveMarketHead
            snapshot={displaySnapshot}
            loading={loading}
            visibleMarkets={activeMarkets}
          />
          {benchmarkControl?.(headContext)}
        </div>
      </header>
      <div className="folio-performance__chart-wrap">
        <FolioNavCurveChart
          performance={performance}
          orders={orders}
          loading={loading}
          benchmarkSymbols={benchmarkSymbols}
          benchmarkCatalog={benchmarkCatalog}
          visibleMarkets={activeMarkets}
          hoverDate={hoverDate}
          onHoverDateChange={setHoverDate}
          windowRebasedByMarket={windowRebasedByMarket}
        />
      </div>
    </>
  );
}
