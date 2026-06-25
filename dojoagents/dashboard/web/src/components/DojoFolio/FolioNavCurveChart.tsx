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
import type { FolioPerformanceView } from '../../types/dojoFolio';
import type { MarketCode } from '../../types/dojoMesh';
import { formatSignedPercent, priceTickValues } from '../../utils/coreCharts';
import { MARKET_CODE, MARKET_FLAG } from '../../utils/marketDisplay';
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
  formatPerformanceAsOfDate,
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
} from '../../utils/spherePerformanceSeries';

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
  benchmarkPath: string;
  layers: Array<{ market: MarketCode; portfolioPath: string }>;
}

function buildFolioVisibleChart(
  performance: FolioPerformanceView,
  visibleByMarket: Partial<Record<MarketCode, MarketSeriesPoint[]>>,
  visibleDates: string[],
  benchmarkSymbol: string | null,
): FolioChartGeometry | null {
  const layers = MARKETS.map((market) => {
    const source = visibleByMarket[market];
    if (!source || source.length < 2) return null;
    const points = alignMarketSeriesToMasterDates(visibleDates, source);
    if (points.length < 2) return null;
    return { market, points };
  }).filter(Boolean) as Array<{ market: MarketCode; points: MarketSeriesPoint[] }>;

  if (layers.length === 0 || visibleDates.length < 2) return null;

  const benchmarkSource = pickBenchmarkSeries(performance, benchmarkSymbol);
  const benchmarkValues =
    benchmarkSource.length >= 2
      ? alignSeriesToDates(
          visibleDates,
          benchmarkSource,
          visibleDates.map(() => 100),
        )
      : null;

  const values = layers.flatMap((layer) => layer.points.map((point) => point.value));
  if (benchmarkValues) values.push(...benchmarkValues);

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
    benchmarkPath:
      benchmarkValues && benchmarkValues.length >= 2
        ? buildIndependentMarketPath(
            benchmarkValues.map((value, index) => ({
              date: visibleDates[index] ?? '',
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
  loading?: boolean;
  benchmarkSymbol?: string | null;
  hoverDate?: string | null;
  onHoverDateChange?: (date: string | null) => void;
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
) {
  const rebasedByMarket = useMemo(() => {
    if (!performance) return {} as Partial<Record<MarketCode, MarketSeriesPoint[]>>;
    const result: Partial<Record<MarketCode, MarketSeriesPoint[]>> = {};
    for (const market of MARKETS) {
      const raw = toMarketSeriesPoints(normalizeSeries(performance.seriesByMarket[market]));
      if (raw.length >= 2) {
        result[market] = rebaseMarketSeries(raw);
      }
    }
    return result;
  }, [performance]);

  const master = useMemo(
    () => pickMasterMarketSeries(rebasedByMarket, MARKETS),
    [rebasedByMarket],
  );

  const chart = useMemo(() => {
    if (!performance) return null;

    const layers = MARKETS.map((market) => {
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
  }, [benchmarkSymbol, performance, rebasedByMarket]);

  const defaultSnapshot = useMemo(
    () => buildLatestCumulativeSnapshot(rebasedByMarket, MARKETS),
    [rebasedByMarket],
  );

  return { rebasedByMarket, master, chart, defaultSnapshot };
}

export function buildFolioNavDisplaySnapshot(
  hoverDate: string | null | undefined,
  rebasedByMarket: Partial<Record<MarketCode, MarketSeriesPoint[]>>,
  defaultSnapshot: PerformanceHeadSnapshot | null,
): PerformanceHeadSnapshot | null {
  if (hoverDate) {
    return buildCumulativeSnapshotForDate(hoverDate, rebasedByMarket, MARKETS);
  }
  return defaultSnapshot;
}

interface FolioNavCurveMarketHeadProps {
  snapshot: PerformanceHeadSnapshot | null;
  loading?: boolean;
}

export function FolioNavCurveMarketHead({
  snapshot,
  loading = false,
}: FolioNavCurveMarketHeadProps) {
  const { t } = useTranslation();

  if (loading) {
    return <span className="folio-performance__head-placeholder">{t('folio.loading')}</span>;
  }

  if (!snapshot?.markets.length) {
    return null;
  }

  const sessionMeta = (() => {
    const dates = snapshot.markets.map((chip) => chip.date);
    const maxDate = dates.reduce((best, date) => (date > best ? date : best), dates[0]);
    const datesDiffer = new Set(dates).size > 1;
    return { maxDate, datesDiffer };
  })();

  return (
    <div className="folio-performance__inline-markets">
      {MARKETS.flatMap((market) => {
        const chip = snapshot.markets.find((item) => item.market === market);
        if (!chip) return [];
        const isClosed = sessionMeta.datesDiffer && chip.date < sessionMeta.maxDate;
        return [
          <span
            key={market}
            className={`folio-performance__inline-market folio-performance__inline-market--${PERFORMANCE_MARKET_CLASS[market]}`}
          >
            <span className="folio-performance__inline-flag" aria-hidden>
              {MARKET_FLAG[market]}
            </span>
            <span className="folio-performance__inline-code">{MARKET_CODE[market]}</span>
            <span
              className={`folio-performance__inline-return folio-performance__inline-return--${
                chip.value >= 100 ? 'up' : 'down'
              }`}
            >
              {formatPerformanceReturnPercent(chip.value)}
            </span>
            <span
              className={
                isClosed
                  ? 'folio-performance__inline-date folio-performance__inline-date--closed'
                  : 'folio-performance__inline-date'
              }
            >
              {formatPerformanceAsOfDate(chip.date)}
            </span>
          </span>,
        ];
      })}
    </div>
  );
}

export function FolioNavCurveChart({
  performance,
  loading = false,
  benchmarkSymbol = null,
  hoverDate = null,
  onHoverDateChange,
}: FolioNavCurveChartProps) {
  const { t } = useTranslation();
  const chartRef = useRef<HTMLDivElement>(null);
  const plotRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{ startX: number; view: ViewRange } | null>(null);
  const [internalHoverDate, setInternalHoverDate] = useState<string | null>(null);
  const [viewRange, setViewRange] = useState<ViewRange>(FULL_VIEW);
  const [isDragging, setIsDragging] = useState(false);
  const activeHoverDate = onHoverDateChange ? hoverDate : internalHoverDate;
  const setHoverDate = onHoverDateChange ?? setInternalHoverDate;

  const { rebasedByMarket, master } = useFolioNavCurveModel(performance, benchmarkSymbol);

  const masterKey = master?.series.map((point) => point.date).join('|') ?? '';

  useEffect(() => {
    setViewRange(FULL_VIEW);
  }, [masterKey, benchmarkSymbol]);

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
    for (const market of MARKETS) {
      const sliced = sliceMarketSeriesByDateRange(rebasedByMarket[market] ?? [], startDate, endDate);
      if (sliced.length >= 2) {
        result[market] = sliced;
      }
    }
    return result;
  }, [performance, rebasedByMarket, visibleWindow]);

  const chart = useMemo(() => {
    if (!performance) return null;
    return buildFolioVisibleChart(
      performance,
      visibleByMarket,
      visibleWindow.series.map((point) => point.date),
      benchmarkSymbol,
    );
  }, [benchmarkSymbol, performance, visibleByMarket, visibleWindow.series]);

  const yAxisTicks = useMemo(
    () => (chart ? buildReturnAxisTicks(chart.yMin, chart.yMax) : []),
    [chart],
  );

  const axisEndLabel = useMemo(
    () => buildMixedAxisEndLabel(latestMarketDates(rebasedByMarket)),
    [rebasedByMarket],
  );

  const displayGeometry = useMemo(() => {
    if (isDragging || !activeHoverDate || !chart) return null;

    const localIndex = findVisibleIndexForDate(visibleWindow.series, activeHoverDate);
    if (localIndex == null) return null;

    const count = visibleWindow.series.length;
    const x = indexToChartX(localIndex, count, CHART_W, PAD_X);
    const anchorSnapshot = buildHoverSnapshotForDate(activeHoverDate, rebasedByMarket, MARKETS);
    if (!anchorSnapshot) return null;

    const dots = MARKETS.map((market) => {
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
  }, [activeHoverDate, chart, isDragging, rebasedByMarket, visibleWindow.series]);

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

  const handleMouseLeave = useCallback(() => {
    endDrag();
    setHoverDate(null);
  }, [endDrag, setHoverDate]);

  if (!chart) {
    return (
      <p className="folio-performance__empty">
        {loading ? t('folio.loading') : t('folio.noPerformanceData')}
      </p>
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
            {chart.benchmarkPath ? (
              <path
                d={chart.benchmarkPath}
                className="folio-performance__line folio-performance__line--benchmark"
              />
            ) : null}
            {chart.layers.map((layer) => (
              <path
                key={layer.market}
                d={layer.portfolioPath}
                className={`folio-performance__line folio-performance__line--${PERFORMANCE_MARKET_CLASS[layer.market]}`}
              />
            ))}
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

interface FolioNavCurveSectionProps {
  performance: FolioPerformanceView | null | undefined;
  loading?: boolean;
  benchmarkSymbol?: string | null;
  benchmarkControl?: ReactNode;
}

export function FolioNavCurveSection({
  performance,
  loading = false,
  benchmarkSymbol = null,
  benchmarkControl,
}: FolioNavCurveSectionProps) {
  const { t } = useTranslation();
  const [hoverDate, setHoverDate] = useState<string | null>(null);
  const { rebasedByMarket, defaultSnapshot } = useFolioNavCurveModel(performance, benchmarkSymbol);
  const displaySnapshot = buildFolioNavDisplaySnapshot(hoverDate, rebasedByMarket, defaultSnapshot);

  return (
    <>
      <header className="folio-card__head folio-performance__head">
        <h3 className="folio-card__title">{t('folio.navCurve')}</h3>
        <div className="folio-performance__head-tail">
          <FolioNavCurveMarketHead snapshot={displaySnapshot} loading={loading} />
          {benchmarkControl}
        </div>
      </header>
      <div className="folio-performance__chart-wrap">
        <FolioNavCurveChart
          performance={performance}
          loading={loading}
          benchmarkSymbol={benchmarkSymbol}
          hoverDate={hoverDate}
          onHoverDateChange={setHoverDate}
        />
      </div>
    </>
  );
}
