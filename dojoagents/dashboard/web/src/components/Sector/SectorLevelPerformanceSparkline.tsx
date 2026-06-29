import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
} from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import type { MarketCode } from '../../types/market';
import type { SectorPerformanceMarketPoint } from '../../types/sector';
import { MARKET_CODE, MARKET_FLAG_IMAGE } from '../../utils/marketDisplay';
import {
  PERFORMANCE_MARKET_CLASS,
  PERFORMANCE_MARKETS,
  buildIndependentMarketPath,
  buildHoverSnapshotForDate,
  buildLatestOneDayReturnSnapshot,
  buildMixedAxisEndLabel,
  buildOneDayReturnSnapshotForDate,
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
} from '../../utils/sectorPerformanceSeries';

interface SectorLevelPerformanceSparklineProps {
  seriesByMarket?: Partial<Record<MarketCode, SectorPerformanceMarketPoint[]>>;
  loading?: boolean;
  hoverDate?: string | null;
  onHoverDateChange?: (date: string | null) => void;
}

interface ViewRange {
  start: number;
  end: number;
}

const CHART_WIDTH = 400;
const CHART_HEIGHT = 72;
const PAD_X = 6;
const PAD_Y = 8;
const MIN_VISIBLE_POINTS = 5;
const FULL_VIEW: ViewRange = { start: 0, end: 1 };

export function SectorLevelPerformanceSparkline({
  seriesByMarket,
  loading = false,
  hoverDate = null,
  onHoverDateChange,
}: SectorLevelPerformanceSparklineProps) {
  const { t } = useTranslation();
  const chartRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{ startX: number; view: ViewRange } | null>(null);
  const [viewRange, setViewRange] = useState<ViewRange>(FULL_VIEW);
  const [isDragging, setIsDragging] = useState(false);

  const rebasedByMarket = useMemo(() => {
    const result: Partial<Record<MarketCode, MarketSeriesPoint[]>> = {};
    for (const market of PERFORMANCE_MARKETS) {
      const raw = toMarketSeriesPoints(seriesByMarket?.[market]);
      if (raw.length >= 2) {
        result[market] = rebaseMarketSeries(raw);
      }
    }
    return result;
  }, [seriesByMarket]);

  const master = useMemo(
    () => pickMasterMarketSeries(rebasedByMarket, PERFORMANCE_MARKETS),
    [rebasedByMarket],
  );

  const masterKey = master?.series.map((point) => point.date).join('|') ?? '';

  useEffect(() => {
    setViewRange(FULL_VIEW);
  }, [masterKey]);

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
    if (!startDate || !endDate) return {} as Partial<Record<MarketCode, MarketSeriesPoint[]>>;

    const result: Partial<Record<MarketCode, MarketSeriesPoint[]>> = {};
    for (const market of PERFORMANCE_MARKETS) {
      const sliced = sliceMarketSeriesByDateRange(rebasedByMarket[market] ?? [], startDate, endDate);
      if (sliced.length >= 2) {
        result[market] = sliced;
      }
    }
    return result;
  }, [rebasedByMarket, visibleWindow]);

  const chart = useMemo(() => {
    const activeSeries = PERFORMANCE_MARKETS.map((market) => visibleByMarket[market]).filter(
      (series): series is MarketSeriesPoint[] => Boolean(series?.length),
    );
    if (activeSeries.length === 0) {
      return { paths: {} as Record<MarketCode, string>, yMin: 98, yMax: 102, hasData: false };
    }

    const values = activeSeries.flatMap((series) => series.map((point) => point.value));
    const dataMin = Math.min(...values);
    const dataMax = Math.max(...values);
    const span = dataMax - dataMin || 1;
    const pad = Math.max(span * 0.08, 1.5);
    const yMin = dataMin - pad;
    const yMax = dataMax + pad;

    const paths = Object.fromEntries(
      PERFORMANCE_MARKETS.map((market) => [
        market,
        buildIndependentMarketPath(
          visibleByMarket[market] ?? [],
          CHART_WIDTH,
          CHART_HEIGHT,
          yMin,
          yMax,
          PAD_X,
          PAD_Y,
        ),
      ]),
    ) as Record<MarketCode, string>;

    return { paths, yMin, yMax, hasData: true };
  }, [visibleByMarket]);

  const latestAnchorDate = useMemo(() => {
    const master = pickMasterMarketSeries(rebasedByMarket, PERFORMANCE_MARKETS);
    return master?.series[master.series.length - 1]?.date ?? null;
  }, [rebasedByMarket]);

  const chartAnchorDate = hoverDate ?? latestAnchorDate;

  const defaultSnapshot = useMemo(
    () => buildLatestOneDayReturnSnapshot(rebasedByMarket),
    [rebasedByMarket],
  );

  const displaySnapshot = useMemo(() => {
    if (isDragging) return null;
    if (hoverDate) return buildOneDayReturnSnapshotForDate(hoverDate, rebasedByMarket);
    return defaultSnapshot;
  }, [hoverDate, isDragging, rebasedByMarket, defaultSnapshot]);

  const chartAnchorSnapshot = useMemo(() => {
    if (isDragging || !chartAnchorDate) return null;
    return buildHoverSnapshotForDate(chartAnchorDate, rebasedByMarket);
  }, [chartAnchorDate, isDragging, rebasedByMarket]);

  const displayLocalIndex = useMemo(() => {
    if (isDragging || !chartAnchorDate || !visibleWindow.series.length) return null;
    return findVisibleIndexForDate(visibleWindow.series, chartAnchorDate);
  }, [chartAnchorDate, isDragging, visibleWindow.series]);

  const displayGeometry = useMemo(() => {
    if (displayLocalIndex == null || isDragging || !chart.hasData || !chartAnchorSnapshot) return null;

    const count = visibleWindow.series.length;
    const x = indexToChartX(displayLocalIndex, count, CHART_WIDTH, PAD_X);
    const dots = PERFORMANCE_MARKETS.map((market) => {
      const value = chartAnchorSnapshot.values[market];
      if (value == null) return null;
      return {
        market,
        x,
        y: valueToChartY(value, chart.yMin, chart.yMax, CHART_HEIGHT, PAD_Y),
      };
    }).filter((item): item is { market: MarketCode; x: number; y: number } => item != null);

    return { x, dots };
  }, [
    displayLocalIndex,
    isDragging,
    chart.hasData,
    chart.yMin,
    chart.yMax,
    chartAnchorSnapshot,
    visibleWindow.series.length,
  ]);

  const baselineY =
    chart.hasData && chart.yMax > chart.yMin
      ? valueToChartY(100, chart.yMin, chart.yMax, CHART_HEIGHT, PAD_Y)
      : null;
  const showBaseline =
    baselineY != null && baselineY >= PAD_Y && baselineY <= CHART_HEIGHT - PAD_Y;

  const updateHoverFromClientX = useCallback(
    (clientX: number) => {
      if (!chartRef.current || !visibleWindow.series.length || isDragging || !onHoverDateChange) return;
      const rect = chartRef.current.getBoundingClientRect();
      const ratio = Math.min(Math.max((clientX - rect.left) / rect.width, 0), 1);
      const index = Math.round(ratio * Math.max(visibleWindow.series.length - 1, 0));
      const anchor = visibleWindow.series[index];
      if (anchor) onHoverDateChange(anchor.date);
    },
    [isDragging, onHoverDateChange, visibleWindow.series],
  );

  const clearHoverIfLeavingCharts = useCallback(
    (event: ReactMouseEvent<HTMLDivElement>) => {
      const related = event.relatedTarget;
      if (related instanceof Node && (related as Element).closest?.('.sphere-level-sparkline__chart-wrap')) {
        return;
      }
      if (hoverDate) onHoverDateChange?.(null);
    },
    [hoverDate, onHoverDateChange],
  );

  const handleMouseMove = useCallback(
    (event: ReactMouseEvent<HTMLDivElement>) => {
      if (dragRef.current) {
        const rect = chartRef.current?.getBoundingClientRect();
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
      onHoverDateChange?.(null);
    },
    [master?.series.length, onHoverDateChange, viewRange],
  );

  useEffect(() => {
    if (!isDragging) return;

    const handleWindowMouseUp = () => endDrag();
    const handleWindowMouseMove = (event: MouseEvent) => {
      if (!dragRef.current || !chartRef.current) return;
      const rect = chartRef.current.getBoundingClientRect();
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

      const rect = el.getBoundingClientRect();
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

  const startDate = visibleWindow.startDate || master?.series[0]?.date || '';
  const axisEndLabel = useMemo(
    () => buildMixedAxisEndLabel(latestMarketDates(rebasedByMarket)),
    [rebasedByMarket],
  );

  const sessionMeta = useMemo(() => {
    if (!displaySnapshot?.markets.length) {
      return { maxDate: '', datesDiffer: false };
    }
    const dates = displaySnapshot.markets.map((chip) => chip.date);
    const maxDate = dates.reduce((best, date) => (date > best ? date : best), dates[0]);
    const datesDiffer = new Set(dates).size > 1;
    return { maxDate, datesDiffer };
  }, [displaySnapshot]);

  const marketTitle = useCallback(
    (chip: { date: string }, isClosed: boolean, isLatest: boolean) => {
      const parts = [chip.date];
      if (isClosed) parts.push(t('sectorPage.sessionClosed'));
      if (isLatest) parts.push(t('sectorPage.sessionLatest'));
      return parts.join(' · ');
    },
    [t],
  );

  return (
    <div className="sphere-level-sparkline">
      <div className="sphere-level-sparkline__head">
        <span className="sphere-level-sparkline__label">{t('sectorPage.performanceReturn')}</span>
        <div className="sphere-level-sparkline__head-tail">
          {displaySnapshot ? (
            <div className="sphere-level-sparkline__inline-markets">
              {PERFORMANCE_MARKETS.flatMap((market) => {
                const chip = displaySnapshot.markets.find((item) => item.market === market);
                return chip ? [{ market, chip }] : [];
              }).flatMap(({ market, chip }) => {
                const isClosed = sessionMeta.datesDiffer && chip.date < sessionMeta.maxDate;
                const isLatest = sessionMeta.datesDiffer && chip.date >= sessionMeta.maxDate;
                const item = (
                  <span
                    key={market}
                    className={`sphere-level-sparkline__inline-market sphere-level-sparkline__inline-market--${PERFORMANCE_MARKET_CLASS[market]}`}
                    title={marketTitle(chip, isClosed, isLatest)}
                  >
                    <img className="sphere-level-sparkline__inline-flag" src={MARKET_FLAG_IMAGE[market]} alt="" aria-hidden />
                    <span className="sphere-level-sparkline__inline-code">{MARKET_CODE[market]}</span>
                    <span
                      className={`sphere-level-sparkline__inline-return sphere-level-sparkline__inline-return--${
                        chip.value >= 100 ? 'up' : 'down'
                      }`}
                    >
                      {formatPerformanceReturnPercent(chip.value)}
                    </span>
                    <span
                      className={
                        isClosed
                          ? 'sphere-level-sparkline__inline-date sphere-level-sparkline__inline-date--closed'
                          : 'sphere-level-sparkline__inline-date'
                      }
                    >
                      {formatPerformanceAsOfDate(chip.date)}
                    </span>
                  </span>
                );
                return [item];
              })}
            </div>
          ) : loading ? (
            <span className="sphere-level-sparkline__head-placeholder">{t('sectorPage.loadingPerformance')}</span>
          ) : null}
        </div>
      </div>
      <div
        ref={chartRef}
        className={`sphere-level-sparkline__chart-wrap${isDragging ? ' sphere-level-sparkline__chart-wrap--dragging' : ''}`}
        onMouseMove={handleMouseMove}
        onMouseDown={handleMouseDown}
        onMouseUp={endDrag}
        onMouseLeave={(event) => {
          endDrag();
          clearHoverIfLeavingCharts(event);
        }}
      >
        {loading ? (
          <p className="sphere-level-sparkline__status">{t('sectorPage.loadingPerformance')}</p>
        ) : !chart.hasData ? (
          <p className="sphere-level-sparkline__status">{t('sectorPage.noPerformanceData')}</p>
        ) : (
          <svg
            className="sphere-level-sparkline__chart"
            viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
            preserveAspectRatio="none"
            aria-hidden
          >
            {showBaseline && (
              <line
                x1={PAD_X}
                y1={baselineY!}
                x2={CHART_WIDTH - PAD_X}
                y2={baselineY!}
                className="sphere-level-sparkline__baseline"
              />
            )}
            {PERFORMANCE_MARKETS.map((market) => {
              const path = chart.paths[market];
              if (!path) return null;
              return (
                <path
                  key={market}
                  d={path}
                  className={`sphere-level-sparkline__line sphere-level-sparkline__line--${PERFORMANCE_MARKET_CLASS[market]}`}
                />
              );
            })}
            {displayGeometry ? (
              <>
                <line
                  x1={displayGeometry.x}
                  y1={PAD_Y}
                  x2={displayGeometry.x}
                  y2={CHART_HEIGHT - PAD_Y}
                  className="sphere-level-sparkline__crosshair"
                />
                {displayGeometry.dots.map((dot) => (
                  <circle
                    key={dot.market}
                    cx={dot.x}
                    cy={dot.y}
                    r={3.2}
                    className={`sphere-level-sparkline__hover-dot sphere-level-sparkline__hover-dot--${PERFORMANCE_MARKET_CLASS[dot.market]}`}
                  />
                ))}
              </>
            ) : null}
          </svg>
        )}
      </div>
      <div className="sphere-level-sparkline__axis" aria-hidden>
        <span className="sphere-level-sparkline__axis-tick sphere-level-sparkline__axis-tick--start">
          {startDate}
        </span>
        <span
          className={`sphere-level-sparkline__axis-tick sphere-level-sparkline__axis-tick--active${
            hoverDate ? ' sphere-level-sparkline__axis-tick--visible' : ''
          }`}
        >
          {hoverDate ?? ''}
        </span>
        <span className="sphere-level-sparkline__axis-tick sphere-level-sparkline__axis-tick--end">
          {axisEndLabel}
        </span>
      </div>
    </div>
  );
};
