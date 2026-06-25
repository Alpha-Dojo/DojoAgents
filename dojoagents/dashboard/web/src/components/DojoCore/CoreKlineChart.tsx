import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from '../../hooks/useTranslation';
import type { CoreChartEvent, CoreKlineBar } from '../../types/dojoCore';
import {
  candleSlot,
  chartY,
  clamp,
  formatPriceAxis,
  formatVolumeCompact,
  movingAverage,
  niceMinMax,
  priceTickValues,
  valueFromChartY,
} from '../../utils/coreCharts';
import { eventMarkerPaths, mapEventsToVisibleMarkers } from '../../utils/coreChartEvents';
import { findClosestDateIndex, findVisibleIndexForLinkedDate, normalizeChartDates } from '../../utils/coreChartLink';
import {
  CORE_CHART_AXIS_W as PRICE_AXIS_W,
  CORE_CHART_MIN_SURFACE_H as MIN_VIEW_H,
  CORE_CHART_MIN_SURFACE_W as MIN_VIEW_W,
  CORE_CHART_PAD_BOTTOM as PAD_BOTTOM,
  CORE_CHART_PAD_TOP as PAD_TOP,
  CORE_CHART_STRIP_H as STRIP_H,
} from '../../utils/coreChartLayout';
import { formatKlineAxisDate, formatKlineDate } from '../../utils/klineDate';
import { CoreCard } from './CoreCard';

const MIN_WINDOW = 16;
const MIN_PLOT_H = 80;
const MIN_PLOT_W = 180;

interface CoreKlineChartProps {
  bars: CoreKlineBar[];
  loading?: boolean;
  /** Reset zoom/pan and layout when the active ticker changes. */
  chartKey?: string;
  chartEvents?: CoreChartEvent[];
  linkedHoverDate?: string | null;
  onLinkedHoverDateChange?: (date: string | null) => void;
}

interface HoverState {
  index: number;
  plotX: number;
  plotY: number;
  cursorPrice: number;
}

interface ViewWindow {
  size: number;
  end: number;
}

function barAmplitude(bar: CoreKlineBar, prevClose: number): number {
  if (prevClose <= 0) return 0;
  return ((bar.high - bar.low) / prevClose) * 100;
}

function barChange(bar: CoreKlineBar, prevClose: number): { change: number; changePct: number } {
  if (prevClose <= 0) return { change: 0, changePct: 0 };
  const change = bar.close - prevClose;
  return { change, changePct: (change / prevClose) * 100 };
}

function barDirection(bar: CoreKlineBar, prevClose: number): 'up' | 'down' {
  if (prevClose > 0) return bar.close >= prevClose ? 'up' : 'down';
  return bar.close >= bar.open ? 'up' : 'down';
}

function formatSigned(value: number, digits = 2): string {
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toFixed(digits)}`;
}

function normalizeViewWindow(barsLength: number, window: ViewWindow): ViewWindow {
  if (barsLength <= 0) {
    return { size: MIN_WINDOW, end: 0 };
  }
  const size = clamp(Math.round(window.size), MIN_WINDOW, barsLength);
  const end = clamp(Math.round(window.end), size, barsLength);
  return { size, end };
}

function buildDefaultWindow(barsLength: number): ViewWindow {
  if (barsLength <= 0) return { size: MIN_WINDOW, end: 0 };
  return { size: barsLength, end: barsLength };
}

function buildMaPath(
  series: Array<number | null>,
  visibleBars: CoreKlineBar[],
  min: number,
  max: number,
  plotW: number,
  plotX0: number,
  priceH: number,
): string {
  const parts: string[] = [];
  let segment: string[] = [];

  series.forEach((value, i) => {
    if (value == null) {
      if (segment.length >= 2) {
        parts.push(`M ${segment[0]} L ${segment.slice(1).join(' L ')}`);
      }
      segment = [];
      return;
    }
    const { cx } = candleSlot(i, visibleBars.length, plotW, plotX0);
    const y = chartY(value, min, max, priceH, PAD_TOP, PAD_BOTTOM);
    segment.push(`${cx},${y}`);
  });

  if (segment.length >= 2) {
    parts.push(`M ${segment[0]} L ${segment.slice(1).join(' L ')}`);
  }
  return parts.join(' ');
}

export function CoreKlineChart({
  bars,
  loading = false,
  chartKey = '',
  chartEvents = [],
  linkedHoverDate = null,
  onLinkedHoverDateChange,
}: CoreKlineChartProps) {
  const { t } = useTranslation();
  const chartPlotsRef = useRef<HTMLDivElement>(null);
  const mainPlotRef = useRef<HTMLDivElement>(null);
  const wheelFrameRef = useRef<number | null>(null);
  const pendingZoomRef = useRef(0);
  const dragRef = useRef<{ startX: number; end: number; size: number } | null>(null);
  const [viewSize, setViewSize] = useState({ w: 640, h: MIN_VIEW_H });
  const [viewWindow, setViewWindow] = useState<ViewWindow>(() => buildDefaultWindow(bars.length));
  const [hover, setHover] = useState<HoverState | null>(null);
  const [plotPointerInside, setPlotPointerInside] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [eventTip, setEventTip] = useState<{ id: string; text: string; x: number; y: number } | null>(
    null,
  );

  const showChartShell = loading || bars.length > 0;

  useLayoutEffect(() => {
    if (bars.length <= 0) return;
    setViewWindow(buildDefaultWindow(bars.length));
    setHover(null);
    setPlotPointerInside(false);
  }, [chartKey, bars.length]);

  useLayoutEffect(() => {
    if (!showChartShell) return;
    const el = mainPlotRef.current;
    if (!el) return;

    const updateSize = () => {
      const rect = el.getBoundingClientRect();
      const width = Number.isFinite(rect.width) ? rect.width : MIN_VIEW_W;
      const height = Number.isFinite(rect.height) ? rect.height : MIN_VIEW_H;
      setViewSize({
        w: Math.max(MIN_VIEW_W, Math.floor(width)),
        h: Math.max(1, Math.floor(height)),
      });
    };

    updateSize();
    const observer = new ResizeObserver(() => updateSize());
    observer.observe(el);
    return () => observer.disconnect();
  }, [showChartShell]);

  const normalizedWindow = useMemo(
    () => normalizeViewWindow(bars.length, viewWindow),
    [bars.length, viewWindow],
  );

  const visibleBars = useMemo(() => {
    if (!bars.length) return [];
    const start = Math.max(0, normalizedWindow.end - normalizedWindow.size);
    return bars.slice(start, normalizedWindow.end);
  }, [bars, normalizedWindow.end, normalizedWindow.size]);

  const visibleStartIndex = Math.max(0, normalizedWindow.end - normalizedWindow.size);

  const layout = useMemo(() => {
    const plotW = Math.max(MIN_PLOT_W, viewSize.w - PRICE_AXIS_W - 4);
    const priceH = Math.max(MIN_PLOT_H, viewSize.h);
    const W = PRICE_AXIS_W + plotW + 4;
    return {
      W,
      H: priceH,
      plotX0: PRICE_AXIS_W,
      plotX1: PRICE_AXIS_W + plotW,
      plotW,
      priceH,
    };
  }, [viewSize]);

  const stripLayout = useMemo(() => {
    const plotW = Math.max(MIN_PLOT_W, viewSize.w - PRICE_AXIS_W - 4);
    const W = PRICE_AXIS_W + plotW + 4;
    return {
      W,
      H: STRIP_H,
      plotX0: PRICE_AXIS_W,
      plotX1: PRICE_AXIS_W + plotW,
      plotW,
    };
  }, [viewSize.w]);

  const chart = useMemo(() => {
    if (!visibleBars.length) {
      return {
        min: 0,
        max: 1,
        ma5: [] as Array<number | null>,
        ma10: [] as Array<number | null>,
        ma20: [] as Array<number | null>,
        volMax: 1,
        ticks: [0, 1],
      };
    }
    const prices = visibleBars.flatMap((b) => [b.high, b.low]);
    const { min, max } = niceMinMax(prices, 0.04);
    const closes = visibleBars.map((b) => b.close);
    const volMax = Math.max(...visibleBars.map((b) => b.volume), 1);
    return {
      min,
      max,
      ma5: movingAverage(closes, 5),
      ma10: movingAverage(closes, 10),
      ma20: movingAverage(closes, 20),
      volMax,
      ticks: priceTickValues(min, max, 5),
    };
  }, [visibleBars]);

  const applyZoom = useCallback(
    (deltaY: number) => {
      if (!bars.length) return;
      pendingZoomRef.current += deltaY;
      if (wheelFrameRef.current != null) return;

      wheelFrameRef.current = window.requestAnimationFrame(() => {
        wheelFrameRef.current = null;
        const accumulated = pendingZoomRef.current;
        pendingZoomRef.current = 0;
        if (!accumulated) return;

        const factor = Math.exp(accumulated * 0.0015);
        setHover(null);
        setViewWindow((current) => {
          const normalized = normalizeViewWindow(bars.length, current);
          const nextSize = clamp(
            Math.round(normalized.size * factor),
            MIN_WINDOW,
            bars.length,
          );
          const end = clamp(normalized.end, nextSize, bars.length);
          return { size: nextSize, end };
        });
      });
    },
    [bars.length],
  );

  const applyPan = useCallback(
    (steps: number) => {
      if (!bars.length || !steps) return;
      setHover(null);
      setViewWindow((current) => {
        const normalized = normalizeViewWindow(bars.length, current);
        const end = clamp(normalized.end + steps, normalized.size, bars.length);
        return { size: normalized.size, end };
      });
    },
    [bars.length],
  );

  useEffect(() => {
    const el = mainPlotRef.current;
    if (!el || !bars.length) return;

    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      event.stopPropagation();

      const absX = Math.abs(event.deltaX);
      const absY = Math.abs(event.deltaY);
      const pinchZoom = event.ctrlKey || event.metaKey;
      const verticalZoom = absY >= absX;

      if (pinchZoom || verticalZoom) {
        applyZoom(event.deltaY);
        return;
      }
      if (absX > 0.5) {
        const step = clamp(Math.round(absX / 12), 1, 8);
        applyPan(event.deltaX > 0 ? -step : step);
      }
    };

    el.addEventListener('wheel', onWheel, { passive: false });
    return () => {
      el.removeEventListener('wheel', onWheel);
      if (wheelFrameRef.current != null) {
        window.cancelAnimationFrame(wheelFrameRef.current);
        wheelFrameRef.current = null;
      }
      pendingZoomRef.current = 0;
    };
  }, [bars.length, applyZoom, applyPan]);

  const handlePointerDown = useCallback(
    (event: React.PointerEvent<SVGRectElement>) => {
      if (event.button !== 0 || !bars.length) return;
      event.preventDefault();
      dragRef.current = {
        startX: event.clientX,
        end: normalizedWindow.end,
        size: normalizedWindow.size,
      };
      setDragging(true);
      setHover(null);
    },
    [bars.length, normalizedWindow.end, normalizedWindow.size],
  );

  useEffect(() => {
    if (!dragging) return;

    const handleMove = (event: PointerEvent) => {
      const drag = dragRef.current;
      const el = mainPlotRef.current;
      if (!drag || !el) return;

      const rect = el.getBoundingClientRect();
      const plotWidth = rect.width * (layout.plotW / layout.W);
      if (plotWidth <= 0) return;

      const dx = event.clientX - drag.startX;
      const shift = Math.round((dx / plotWidth) * drag.size);
      const end = clamp(drag.end - shift, drag.size, bars.length);
      setViewWindow({ size: drag.size, end });
    };

    const handleUp = () => {
      dragRef.current = null;
      setDragging(false);
    };

    window.addEventListener('pointermove', handleMove);
    window.addEventListener('pointerup', handleUp);
    return () => {
      window.removeEventListener('pointermove', handleMove);
      window.removeEventListener('pointerup', handleUp);
    };
  }, [dragging, bars.length, layout.plotW, layout.W]);

  const handlePointerMove = useCallback(
    (event: React.PointerEvent<SVGRectElement>) => {
      if (dragRef.current) return;
      if (!visibleBars.length || layout.plotW <= 0 || layout.priceH <= 0) return;
      const svg = event.currentTarget.ownerSVGElement;
      if (!svg) return;
      const rect = svg.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) return;

      const scaleX = layout.W / rect.width;
      const scaleY = layout.H / rect.height;
      const x = (event.clientX - rect.left) * scaleX;
      const y = (event.clientY - rect.top) * scaleY;

      if (x < layout.plotX0 || x > layout.plotX1 || y < PAD_TOP || y > layout.priceH) {
        setPlotPointerInside(false);
        setHover(null);
        onLinkedHoverDateChange?.(null);
        return;
      }

      setPlotPointerInside(true);
      const slot = layout.plotW / visibleBars.length;
      const index = clamp(Math.floor((x - layout.plotX0) / slot), 0, visibleBars.length - 1);
      const { cx } = candleSlot(index, visibleBars.length, layout.plotW, layout.plotX0);
      const cursorPrice = valueFromChartY(y, chart.min, chart.max, layout.priceH, PAD_TOP, PAD_BOTTOM);

      setHover({ index, plotX: cx, plotY: y, cursorPrice });
      onLinkedHoverDateChange?.(formatKlineDate(visibleBars[index].date));
    },
    [visibleBars, layout, chart.min, chart.max, onLinkedHoverDateChange],
  );

  useEffect(() => {
    if (!linkedHoverDate) {
      if (!plotPointerInside) setHover(null);
      return;
    }
    if (dragging || !visibleBars.length) return;

    const visibleIndex = findVisibleIndexForLinkedDate(
      visibleBars,
      linkedHoverDate,
      visibleStartIndex,
      bars,
    );
    if (visibleIndex == null) {
      setHover(null);
      return;
    }

    const bar = visibleBars[visibleIndex];
    const { cx } = candleSlot(visibleIndex, visibleBars.length, layout.plotW, layout.plotX0);
    const plotY = chartY(bar.close, chart.min, chart.max, layout.priceH, PAD_TOP, PAD_BOTTOM);
    setHover({ index: visibleIndex, plotX: cx, plotY, cursorPrice: bar.close });
  }, [
    linkedHoverDate,
    plotPointerInside,
    dragging,
    visibleBars,
    visibleStartIndex,
    bars,
    layout.plotW,
    layout.plotX0,
    layout.priceH,
    chart.min,
    chart.max,
  ]);

  const externalDisplayBar = useMemo(() => {
    if (!linkedHoverDate || hover) return null;
    const idx = findClosestDateIndex(normalizeChartDates(bars), linkedHoverDate);
    return idx >= 0 ? bars[idx] : null;
  }, [linkedHoverDate, hover, bars]);

  const displayBar =
    (hover ? visibleBars[hover.index] : null) ??
    externalDisplayBar ??
    (visibleBars.length ? visibleBars[visibleBars.length - 1] : null);
  const displayBarGlobalIndex = useMemo(() => {
    if (!displayBar) return -1;
    const date = formatKlineDate(displayBar.date);
    return findClosestDateIndex(normalizeChartDates(bars), date);
  }, [displayBar, bars]);
  const displayPrevClose =
    displayBarGlobalIndex > 0
      ? bars[displayBarGlobalIndex - 1].close
      : displayBar?.open ?? 0;
  const displayChange = displayBar ? barChange(displayBar, displayPrevClose) : null;
  const displayAmplitude = displayBar ? barAmplitude(displayBar, displayPrevClose) : 0;
  const displayDirection = displayBar ? barDirection(displayBar, displayPrevClose) : 'up';
  const isHovering = hover != null || externalDisplayBar != null;
  const showCrosshair = Boolean(hover && !dragging && (plotPointerInside || linkedHoverDate));
  const crosshair = showCrosshair ? hover : null;

  const canRenderChart = visibleBars.length > 0 && layout.plotW > 0 && layout.priceH > 0;

  const axisTicks = useMemo(() => {
    if (!visibleBars.length) return [];
    const startDate = formatKlineDate(visibleBars[0].date);
    const endDate = formatKlineDate(visibleBars[visibleBars.length - 1].date);
    const spanYears = startDate.slice(0, 4) !== endDate.slice(0, 4);
    const midIndex = Math.floor((visibleBars.length - 1) / 2);
    const midDate = formatKlineDate(visibleBars[midIndex].date);
    const ticks = [
      { date: startDate, align: 'start' as const },
      ...(visibleBars.length > 2 ? [{ date: midDate, align: 'center' as const }] : []),
      { date: endDate, align: 'end' as const },
    ];
    return ticks.map((tick) => ({
      ...tick,
      label: formatKlineAxisDate(tick.date, spanYears),
    }));
  }, [visibleBars]);

  const activeBarDate = displayBar ? formatKlineDate(displayBar.date) : null;

  const priceTickPositions = useMemo(() => {
    if (!canRenderChart) return [];
    return chart.ticks.map((tick) => {
      const y = chartY(tick, chart.min, chart.max, layout.priceH, PAD_TOP, PAD_BOTTOM);
      return {
        tick,
        topPct: (y / layout.priceH) * 100,
      };
    });
  }, [canRenderChart, chart.ticks, chart.min, chart.max, layout.priceH]);

  const maPaths = useMemo(
    () => ({
      ma5: buildMaPath(chart.ma5, visibleBars, chart.min, chart.max, layout.plotW, layout.plotX0, layout.priceH),
      ma10: buildMaPath(chart.ma10, visibleBars, chart.min, chart.max, layout.plotW, layout.plotX0, layout.priceH),
      ma20: buildMaPath(chart.ma20, visibleBars, chart.min, chart.max, layout.plotW, layout.plotX0, layout.priceH),
    }),
    [chart, visibleBars, layout.plotW, layout.plotX0, layout.priceH],
  );

  const eventMarkers = useMemo(
    () =>
      mapEventsToVisibleMarkers(
        chartEvents,
        visibleBars,
        visibleStartIndex,
        bars,
        layout.plotW,
        layout.plotX0,
      ),
    [chartEvents, visibleBars, visibleStartIndex, bars, layout.plotW, layout.plotX0],
  );

  const eventMarkerTopY = PAD_TOP - 2;

  return (
    <CoreCard className="core-card--kline">
      {!showChartShell ? (
        <p className="core-chart-stage__status">{t('core.klineEmpty')}</p>
      ) : null}

      {showChartShell ? (
        <div className={`core-chart-shell${isHovering ? ' core-chart-shell--hover' : ''}`}>
          <div className={`core-kline__topbar${isHovering ? ' core-kline__topbar--hover' : ''}`}>
            <span className="core-kline__topbar-title">{t('core.klineTitle')}</span>
            {displayBar && displayChange ? (
              <div className="core-kline__topbar-fields" aria-live="polite">
                  <time className="core-kline__field core-kline__field--date" dateTime={formatKlineDate(displayBar.date)}>
                    <i>{t('core.klineDate')}</i>
                    <b>{formatKlineDate(displayBar.date)}</b>
                  </time>
                  <span className="core-kline__field">
                    <i>{t('core.klineOpen')}</i>
                    <b className={`core-kline__val--${displayDirection}`}>
                      {formatPriceAxis(displayBar.open)}
                    </b>
                  </span>
                  <span className="core-kline__field">
                    <i>{t('core.klineHigh')}</i>
                    <b className={`core-kline__val--${displayDirection}`}>
                      {formatPriceAxis(displayBar.high)}
                    </b>
                  </span>
                  <span className="core-kline__field">
                    <i>{t('core.klineLow')}</i>
                    <b className={`core-kline__val--${displayDirection}`}>
                      {formatPriceAxis(displayBar.low)}
                    </b>
                  </span>
                  <span className="core-kline__field">
                    <i>{t('core.klineClose')}</i>
                    <b className={`core-kline__val--${displayDirection}`}>
                      {formatPriceAxis(displayBar.close)}
                    </b>
                  </span>
                  <span className="core-kline__field">
                    <i>{t('core.klineAmount')}</i>
                    <b className={`core-kline__val--${displayDirection}`}>
                      {formatVolumeCompact(displayBar.amount)}
                    </b>
                  </span>
                  <span className="core-kline__field">
                    <i>{t('core.klineChangePct')}</i>
                    <b className={`core-kline__val--${displayDirection}`}>
                      {formatSigned(displayChange.changePct)}%
                    </b>
                  </span>
                  <span className="core-kline__field">
                    <i>{t('core.klineAmplitude')}</i>
                    <b className={`core-kline__val--${displayDirection}`}>
                      {displayAmplitude.toFixed(2)}%
                    </b>
                  </span>
                </div>
              ) : null}
            </div>

            <div className="core-chart-plots" ref={chartPlotsRef}>
              <div
                className={`core-chart-main-pane${dragging ? ' core-kline__chart-surface--dragging' : ''}`}
                ref={mainPlotRef}
              >
                {canRenderChart ? (
                  <>
                    <div className="core-kline__price-axis" aria-hidden>
                      {priceTickPositions.map(({ tick, topPct }) => (
                        <span
                          key={tick}
                          className="core-kline__price-tick"
                          style={{ top: `${topPct}%` }}
                        >
                          {formatPriceAxis(tick)}
                        </span>
                      ))}
                    </div>
                    <svg
                      viewBox={`0 0 ${layout.W} ${layout.H}`}
                      preserveAspectRatio="none"
                      className="core-kline__svg"
                      role="img"
                      aria-hidden="true"
                    >
                      <rect x={0} y={0} width={layout.W} height={layout.H} className="core-kline__canvas-bg" />
                      <rect
                        x={layout.plotX0}
                        y={PAD_TOP}
                        width={layout.plotW}
                        height={layout.priceH - PAD_TOP}
                        className="core-kline__plot-bg"
                      />

                      {chart.ticks.map((tick, tickIndex) => {
                        const y = chartY(tick, chart.min, chart.max, layout.priceH, PAD_TOP, PAD_BOTTOM);
                        return (
                          <line
                            key={`${tick}-${tickIndex}`}
                            x1={layout.plotX0}
                            x2={layout.plotX1}
                            y1={y}
                            y2={y}
                            className="core-kline__grid"
                          />
                        );
                      })}

                      {eventMarkers.map(({ event, cx }) => {
                        const paths = eventMarkerPaths(cx, eventMarkerTopY);
                        const hoverText = t('core.chartEventHover.earnings', {
                          date: event.date,
                          quarter: event.quarterCode,
                        });
                        const isActive = eventTip?.id === event.id;
                        return (
                          <g
                            key={event.id}
                            className={`core-kline__event-marker core-kline__event-marker--${event.kind}${
                              isActive ? ' core-kline__event-marker--active' : ''
                            }`}
                            aria-label={hoverText}
                            onMouseEnter={(e) => {
                              const rect = e.currentTarget.getBoundingClientRect();
                              setEventTip({
                                id: event.id,
                                text: hoverText,
                                x: rect.left + rect.width / 2,
                                y: rect.top - 6,
                              });
                            }}
                            onMouseLeave={() => setEventTip(null)}
                          >
                            <rect
                              x={paths.hitX}
                              y={paths.hitY}
                              width={paths.hitW}
                              height={paths.hitH}
                              className="core-kline__event-marker-hit"
                            />
                            <line
                              x1={cx}
                              x2={cx}
                              y1={paths.stemTop}
                              y2={paths.stemBottom}
                              className="core-kline__event-marker-stem"
                            />
                            <path d={paths.diamond} className="core-kline__event-marker-badge" />
                          </g>
                        );
                      })}

                      {([
                        ['ma5', maPaths.ma5],
                        ['ma10', maPaths.ma10],
                        ['ma20', maPaths.ma20],
                      ] as const).map(([key, path]) =>
                        path ? <path key={key} d={path} className={`core-kline__ma core-kline__ma--${key}`} /> : null,
                      )}

                      {visibleBars.map((bar, i) => {
                        const { cx, barW } = candleSlot(i, visibleBars.length, layout.plotW, layout.plotX0);
                        const x = cx - barW / 2;
                        const prevClose = i > 0 ? visibleBars[i - 1].close : bar.open;
                        const direction = barDirection(bar, prevClose);
                        const bodyTop = chartY(Math.max(bar.open, bar.close), chart.min, chart.max, layout.priceH, PAD_TOP, PAD_BOTTOM);
                        const bodyBottom = chartY(Math.min(bar.open, bar.close), chart.min, chart.max, layout.priceH, PAD_TOP, PAD_BOTTOM);
                        const bodyH = Math.max(1, bodyBottom - bodyTop);
                        const wickTop = chartY(bar.high, chart.min, chart.max, layout.priceH, PAD_TOP, PAD_BOTTOM);
                        const wickBottom = chartY(bar.low, chart.min, chart.max, layout.priceH, PAD_TOP, PAD_BOTTOM);
                        return (
                          <g key={`candle-${bar.date}-${visibleStartIndex + i}`} shapeRendering="crispEdges">
                            <line
                              x1={cx}
                              x2={cx}
                              y1={wickTop}
                              y2={bodyTop}
                              className={`core-kline__wick core-kline__wick--${direction}`}
                            />
                            <line
                              x1={cx}
                              x2={cx}
                              y1={bodyBottom}
                              y2={wickBottom}
                              className={`core-kline__wick core-kline__wick--${direction}`}
                            />
                            <rect
                              x={x}
                              y={bodyTop}
                              width={barW}
                              height={bodyH}
                              className={`core-kline__body core-kline__body--${direction}`}
                            />
                          </g>
                        );
                      })}

                      {crosshair ? (
                        <g className="core-kline__crosshair">
                          <line
                            x1={crosshair.plotX}
                            x2={crosshair.plotX}
                            y1={PAD_TOP}
                            y2={layout.priceH}
                            className="core-kline__crosshair-v"
                          />
                          <line
                            x1={layout.plotX0}
                            x2={layout.plotX1}
                            y1={crosshair.plotY}
                            y2={crosshair.plotY}
                            className="core-kline__crosshair-h"
                          />
                          <circle
                            cx={crosshair.plotX}
                            cy={chartY(
                              visibleBars[crosshair.index].close,
                              chart.min,
                              chart.max,
                              layout.priceH,
                              PAD_TOP,
                              PAD_BOTTOM,
                            )}
                            r="3.5"
                            className={`core-kline__hover-dot core-kline__hover-dot--${barDirection(
                              visibleBars[crosshair.index],
                              crosshair.index > 0 ? visibleBars[crosshair.index - 1].close : visibleBars[crosshair.index].open,
                            )}`}
                          />
                        </g>
                      ) : null}

                      <rect
                        x={layout.plotX0}
                        y={PAD_TOP}
                        width={layout.plotW}
                        height={layout.priceH - PAD_TOP}
                        className="core-kline__hit"
                        onPointerDown={handlePointerDown}
                        onPointerMove={handlePointerMove}
                        onPointerLeave={() => {
                          if (!dragRef.current) {
                            setPlotPointerInside(false);
                            setHover(null);
                            onLinkedHoverDateChange?.(null);
                          }
                        }}
                      />
                    </svg>
                  </>
                ) : (
                  <p className="core-chart-stage__status">{t('core.klineLoading')}</p>
                )}
              </div>

              <div className="core-chart-time-pane" aria-hidden>
                <div className="core-kline__time-axis">
                  {axisTicks.map(({ date, label, align }) => (
                    <span
                      key={date}
                      className={`core-kline__time-tick core-kline__time-tick--${align}${
                        isHovering && activeBarDate === date ? ' core-kline__time-tick--active' : ''
                      }`}
                    >
                      {label}
                    </span>
                  ))}
                </div>
              </div>

              <div className="core-chart-strip-pane">
                {canRenderChart ? (
                  <svg
                    viewBox={`0 0 ${stripLayout.W} ${stripLayout.H}`}
                    preserveAspectRatio="none"
                    className="core-kline__svg core-kline__svg--strip"
                    role="img"
                    aria-hidden="true"
                  >
                    <rect x={0} y={0} width={stripLayout.W} height={stripLayout.H} className="core-kline__vol-bg" />
                    {visibleBars.map((bar, i) => {
                      const { cx, barW } = candleSlot(i, visibleBars.length, stripLayout.plotW, stripLayout.plotX0);
                      const x = cx - barW / 2;
                      const prevClose = i > 0 ? visibleBars[i - 1].close : bar.open;
                      const direction = barDirection(bar, prevClose);
                      const volH = (bar.volume / chart.volMax) * STRIP_H;
                      return (
                        <rect
                          key={`vol-${bar.date}-${visibleStartIndex + i}`}
                          x={x}
                          y={STRIP_H - volH}
                          width={barW}
                          height={Math.max(1, volH)}
                          className={`core-kline__volume core-kline__volume--${direction}`}
                        />
                      );
                    })}
                  </svg>
                ) : null}
              </div>
            </div>
        </div>
      ) : null}
      {eventTip
        ? createPortal(
            <div
              className="core-kline__event-marker-tooltip"
              style={{ left: eventTip.x, top: eventTip.y }}
              role="tooltip"
            >
              {eventTip.text}
            </div>,
            document.body,
          )
        : null}
    </CoreCard>
  );
}
