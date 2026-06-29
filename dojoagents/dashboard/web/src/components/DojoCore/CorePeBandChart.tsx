import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import type { CorePeBandPoint } from '../../types/dojoCore';
import type { MarketCode } from '../../types/dojoMesh';
import {
  candleSlot,
  chartY,
  clamp,
  formatPeAxis,
  niceMinMax,
  priceTickValues,
  valueFromChartY,
} from '../../utils/coreCharts';
import { findClosestDateIndex, findVisibleIndexForLinkedDate, normalizeChartDates } from '../../utils/coreChartLink';
import { LoadingIndicator } from '../ui/LoadingIndicator';
import {
  CORE_CHART_AXIS_W as AXIS_W,
  CORE_CHART_MIN_SURFACE_H as MIN_VIEW_H,
  CORE_CHART_MIN_SURFACE_W as MIN_VIEW_W,
  CORE_CHART_PAD_BOTTOM as PAD_BOTTOM,
  CORE_CHART_PAD_TOP as PAD_TOP,
} from '../../utils/coreChartLayout';
import { formatKlineAxisDate, formatKlineDate } from '../../utils/klineDate';
import { MARKET_CODE, MARKET_FLAG_IMAGE } from '../../utils/marketDisplay';
import { formatPe } from '../../utils/marketStats';
import { PERFORMANCE_MARKET_CLASS } from '../../utils/spherePerformanceSeries';
import type { SectorLevelKey } from '../../types/dojoSphere';
import { CoreCard } from './CoreCard';

const MIN_WINDOW = 16;
const MIN_PLOT_H = 80;
const MIN_PLOT_W = 180;

const SECTOR_PE_MARKETS: MarketCode[] = ['us', 'cn', 'hk'];
const SECTOR_PE_LEVELS: SectorLevelKey[] = ['L3', 'L2', 'L1'];

interface CorePeBandChartProps {
  points: CorePeBandPoint[];
  loading?: boolean;
  sectorPeByMarket?: Partial<Record<MarketCode, number | null>>;
  sectorPeLoading?: boolean;
  sectorPeLevel?: SectorLevelKey;
  sectorLevelLabels?: Partial<Record<SectorLevelKey, string>>;
  onSectorPeLevelChange?: (level: SectorLevelKey) => void;
  linkedHoverDate?: string | null;
  onLinkedHoverDateChange?: (date: string | null) => void;
}

interface HoverState {
  index: number;
  plotX: number;
  plotY: number;
  cursorPe: number;
}

interface ViewWindow {
  size: number;
  end: number;
}

function normalizeViewWindow(length: number, window: ViewWindow): ViewWindow {
  if (length <= 0) {
    return { size: MIN_WINDOW, end: 0 };
  }
  const size = clamp(Math.round(window.size), MIN_WINDOW, length);
  const end = clamp(Math.round(window.end), size, length);
  return { size, end };
}

function buildDefaultWindow(length: number): ViewWindow {
  if (length <= 0) return { size: MIN_WINDOW, end: 0 };
  return { size: length, end: length };
}

function buildPePath(
  visiblePoints: CorePeBandPoint[],
  min: number,
  max: number,
  plotW: number,
  plotX0: number,
  priceH: number,
): string {
  if (visiblePoints.length < 2) return '';
  return visiblePoints
    .map((point, index) => {
      const { cx } = candleSlot(index, visiblePoints.length, plotW, plotX0);
      return `${cx},${chartY(point.pe, min, max, priceH, PAD_TOP, PAD_BOTTOM)}`;
    })
    .join(' ');
}

export function CorePeBandChart({
  points,
  loading = false,
  sectorPeByMarket = {},
  sectorPeLoading = false,
  sectorPeLevel = 'L3',
  sectorLevelLabels = {},
  onSectorPeLevelChange,
  linkedHoverDate = null,
  onLinkedHoverDateChange,
}: CorePeBandChartProps) {
  const { t } = useTranslation();
  const chartPlotsRef = useRef<HTMLDivElement>(null);
  const mainPlotRef = useRef<HTMLDivElement>(null);
  const wheelFrameRef = useRef<number | null>(null);
  const pendingZoomRef = useRef(0);
  const dragRef = useRef<{ startX: number; end: number; size: number } | null>(null);
  const [viewSize, setViewSize] = useState({ w: 520, h: MIN_VIEW_H });
  const [viewWindow, setViewWindow] = useState<ViewWindow>(() => buildDefaultWindow(points.length));
  const [hover, setHover] = useState<HoverState | null>(null);
  const [plotPointerInside, setPlotPointerInside] = useState(false);
  const [dragging, setDragging] = useState(false);

  useEffect(() => {
    setViewWindow(buildDefaultWindow(points.length));
    setHover(null);
    setPlotPointerInside(false);
  }, [points]);

  useEffect(() => {
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
  }, []);

  const normalizedWindow = useMemo(
    () => normalizeViewWindow(points.length, viewWindow),
    [points.length, viewWindow],
  );

  const visiblePoints = useMemo(() => {
    if (!points.length) return [];
    const start = Math.max(0, normalizedWindow.end - normalizedWindow.size);
    return points.slice(start, normalizedWindow.end);
  }, [points, normalizedWindow.end, normalizedWindow.size]);

  const visibleStartIndex = Math.max(0, normalizedWindow.end - normalizedWindow.size);

  const layout = useMemo(() => {
    const plotW = Math.max(MIN_PLOT_W, viewSize.w - AXIS_W - 4);
    const priceH = Math.max(MIN_PLOT_H, viewSize.h);
    const W = AXIS_W + plotW + 4;
    return {
      W,
      H: priceH,
      plotX0: AXIS_W,
      plotX1: AXIS_W + plotW,
      plotW,
      priceH,
    };
  }, [viewSize]);

  const chart = useMemo(() => {
    if (!visiblePoints.length) {
      return { min: 0, max: 1, ticks: [0, 1] };
    }
    const values = visiblePoints.map((point) => point.pe);
    const { min, max } = niceMinMax(values, 0.05);
    return {
      min,
      max,
      ticks: priceTickValues(min, max, 5),
    };
  }, [visiblePoints]);

  const applyZoom = useCallback(
    (deltaY: number) => {
      if (!points.length) return;
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
          const normalized = normalizeViewWindow(points.length, current);
          const nextSize = clamp(
            Math.round(normalized.size * factor),
            MIN_WINDOW,
            points.length,
          );
          const end = clamp(normalized.end, nextSize, points.length);
          return { size: nextSize, end };
        });
      });
    },
    [points.length],
  );

  const applyPan = useCallback(
    (steps: number) => {
      if (!points.length || !steps) return;
      setHover(null);
      setViewWindow((current) => {
        const normalized = normalizeViewWindow(points.length, current);
        const end = clamp(normalized.end + steps, normalized.size, points.length);
        return { size: normalized.size, end };
      });
    },
    [points.length],
  );

  useEffect(() => {
    const el = mainPlotRef.current;
    if (!el || !points.length) return;

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
  }, [points.length, applyZoom, applyPan]);

  const handlePointerDown = useCallback(
    (event: React.PointerEvent<SVGRectElement>) => {
      if (event.button !== 0 || !points.length) return;
      event.preventDefault();
      dragRef.current = {
        startX: event.clientX,
        end: normalizedWindow.end,
        size: normalizedWindow.size,
      };
      setDragging(true);
      setHover(null);
    },
    [points.length, normalizedWindow.end, normalizedWindow.size],
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
      const end = clamp(drag.end - shift, drag.size, points.length);
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
  }, [dragging, points.length, layout.plotW, layout.W]);

  const handlePointerMove = useCallback(
    (event: React.PointerEvent<SVGRectElement>) => {
      if (dragRef.current) return;
      if (!visiblePoints.length || layout.plotW <= 0 || layout.priceH <= 0) return;
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
      const slot = layout.plotW / visiblePoints.length;
      const index = clamp(Math.floor((x - layout.plotX0) / slot), 0, visiblePoints.length - 1);
      const { cx } = candleSlot(index, visiblePoints.length, layout.plotW, layout.plotX0);
      const cursorPe = valueFromChartY(y, chart.min, chart.max, layout.priceH, PAD_TOP, PAD_BOTTOM);

      setHover({ index, plotX: cx, plotY: y, cursorPe });
      onLinkedHoverDateChange?.(formatKlineDate(visiblePoints[index].date));
    },
    [visiblePoints, layout, chart.min, chart.max, onLinkedHoverDateChange],
  );

  useEffect(() => {
    if (!linkedHoverDate) {
      if (!plotPointerInside) setHover(null);
      return;
    }
    if (dragging || !visiblePoints.length) return;

    const visibleIndex = findVisibleIndexForLinkedDate(
      visiblePoints,
      linkedHoverDate,
      visibleStartIndex,
      points,
    );
    if (visibleIndex == null) {
      setHover(null);
      return;
    }

    const point = visiblePoints[visibleIndex];
    const { cx } = candleSlot(visibleIndex, visiblePoints.length, layout.plotW, layout.plotX0);
    const plotY = chartY(point.pe, chart.min, chart.max, layout.priceH, PAD_TOP, PAD_BOTTOM);
    setHover({ index: visibleIndex, plotX: cx, plotY, cursorPe: point.pe });
  }, [
    linkedHoverDate,
    plotPointerInside,
    dragging,
    visiblePoints,
    visibleStartIndex,
    points,
    layout.plotW,
    layout.plotX0,
    layout.priceH,
    chart.min,
    chart.max,
  ]);

  const externalDisplayPoint = useMemo(() => {
    if (!linkedHoverDate || hover) return null;
    const idx = findClosestDateIndex(normalizeChartDates(points), linkedHoverDate);
    return idx >= 0 ? points[idx] : null;
  }, [linkedHoverDate, hover, points]);

  const displayPoint =
    (hover ? visiblePoints[hover.index] : null) ??
    externalDisplayPoint ??
    (visiblePoints.length ? visiblePoints[visiblePoints.length - 1] : null);
  const isHovering = hover != null || externalDisplayPoint != null;
  const showCrosshair = Boolean(hover && !dragging && (plotPointerInside || linkedHoverDate));
  const crosshair = showCrosshair ? hover : null;
  const canRenderChart = visiblePoints.length > 0 && layout.plotW > 0 && layout.priceH > 0;

  const axisTicks = useMemo(() => {
    if (!visiblePoints.length) return [];
    const startDate = formatKlineDate(visiblePoints[0].date);
    const endDate = formatKlineDate(visiblePoints[visiblePoints.length - 1].date);
    const spanYears = startDate.slice(0, 4) !== endDate.slice(0, 4);
    const midIndex = Math.floor((visiblePoints.length - 1) / 2);
    const midDate = formatKlineDate(visiblePoints[midIndex].date);
    const ticks = [
      { date: startDate, align: 'start' as const },
      ...(visiblePoints.length > 2 ? [{ date: midDate, align: 'center' as const }] : []),
      { date: endDate, align: 'end' as const },
    ];
    return ticks.map((tick) => ({
      ...tick,
      label: formatKlineAxisDate(tick.date, spanYears),
    }));
  }, [visiblePoints]);

  const activePointDate = displayPoint ? formatKlineDate(displayPoint.date) : null;

  const axisTickPositions = useMemo(() => {
    if (!canRenderChart) return [];
    return chart.ticks.map((tick) => {
      const y = chartY(tick, chart.min, chart.max, layout.priceH, PAD_TOP, PAD_BOTTOM);
      return {
        tick,
        topPct: (y / layout.priceH) * 100,
      };
    });
  }, [canRenderChart, chart.ticks, chart.min, chart.max, layout.priceH]);

  const pePath = useMemo(
    () =>
      buildPePath(
        visiblePoints,
        chart.min,
        chart.max,
        layout.plotW,
        layout.plotX0,
        layout.priceH,
      ),
    [visiblePoints, chart.min, chart.max, layout.plotW, layout.plotX0, layout.priceH],
  );

  const sectorPePanel = useMemo(
    () =>
      SECTOR_PE_MARKETS.map((market) => ({
        market,
        pe: sectorPeByMarket[market] ?? null,
        label: formatPe(sectorPeByMarket[market] ?? null),
      })),
    [sectorPeByMarket],
  );

  if (loading && !points.length) {
    return (
      <CoreCard className="core-card--pe-band">
        <div className="core-pe-band">
          <LoadingIndicator
            className="core-chart-stage__status"
            label={t('core.peBandLoading')}
            variant="panel"
          />
        </div>
      </CoreCard>
    );
  }

  if (!points.length) {
    return (
      <CoreCard className="core-card--pe-band">
        <div className="core-pe-band">
          <p className="core-chart-stage__status">{t('core.peBandEmpty')}</p>
        </div>
      </CoreCard>
    );
  }

  return (
    <CoreCard className="core-card--pe-band">
      <div className={`core-chart-shell${isHovering ? ' core-chart-shell--hover' : ''}`}>
        <div className={`core-kline__topbar${isHovering ? ' core-kline__topbar--hover' : ''}`}>
          <span className="core-kline__topbar-title">{t('core.peBandTitle')}</span>
          {displayPoint ? (
            <div className="core-kline__topbar-fields" aria-live="polite">
              <time
                className="core-kline__field core-kline__field--date"
                dateTime={formatKlineDate(displayPoint.date)}
              >
                <i>{t('core.klineDate')}</i>
                <b>{formatKlineDate(displayPoint.date)}</b>
              </time>
              <span className="core-kline__field">
                <i>{t('core.peRatio')}</i>
                <b className="core-pe-band__val--pe">{formatPeAxis(displayPoint.pe)}</b>
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
                  {axisTickPositions.map(({ tick, topPct }) => (
                    <span
                      key={tick}
                      className="core-kline__price-tick"
                      style={{ top: `${topPct}%` }}
                    >
                      {formatPeAxis(tick)}
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

                  {pePath ? <polyline points={pePath} className="core-pe-band__line" /> : null}

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
                          visiblePoints[crosshair.index].pe,
                          chart.min,
                          chart.max,
                          layout.priceH,
                          PAD_TOP,
                          PAD_BOTTOM,
                        )}
                        r="3.5"
                        className="core-pe-band__hover-dot"
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
              <LoadingIndicator
                className="core-chart-stage__status"
                label={t('core.peBandLoading')}
                variant="panel"
              />
            )}
          </div>

          <div className="core-chart-time-pane" aria-hidden>
            <div className="core-kline__time-axis">
              {axisTicks.map(({ date, label, align }) => (
                <span
                  key={date}
                  className={`core-kline__time-tick core-kline__time-tick--${align}${
                    isHovering && activePointDate === date ? ' core-kline__time-tick--active' : ''
                  }`}
                >
                  {label}
                </span>
              ))}
            </div>
          </div>

          <div className="core-chart-strip-pane">
            <div className="core-pe-band__sector-pe" aria-label={t('core.sectorPeTitle')}>
              <div className="core-pe-band__sector-level" role="tablist" aria-label={t('core.sectorPeLevel')}>
                {SECTOR_PE_LEVELS.map((level) => {
                  const active = level === sectorPeLevel;
                  const label = sectorLevelLabels[level];
                  return (
                    <button
                      key={level}
                      type="button"
                      role="tab"
                      aria-selected={active}
                      className={`core-pe-band__sector-level-tab${
                        active ? ' core-pe-band__sector-level-tab--active' : ''
                      }`}
                      onClick={() => onSectorPeLevelChange?.(level)}
                    >
                      <span className="core-pe-band__sector-level-key">{level}</span>
                      {active && label ? (
                        <span className="core-pe-band__sector-level-name">{label}</span>
                      ) : null}
                    </button>
                  );
                })}
              </div>
              <div className="core-pe-band__sector-markets">
                {sectorPePanel.map((item) => (
                  <span
                    key={item.market}
                    className={`core-pe-band__sector-pe-item core-pe-band__sector-pe-item--${PERFORMANCE_MARKET_CLASS[item.market]}${
                      sectorPeLoading ? ' core-pe-band__sector-pe-item--loading' : ''
                    }`}
                  >
                    <img className="core-pe-band__sector-pe-flag" src={MARKET_FLAG_IMAGE[item.market]} alt="" aria-hidden />
                    <span className="core-pe-band__sector-pe-code">{MARKET_CODE[item.market]}</span>
                    <span className="core-pe-band__sector-pe-metric">{t('core.peRatio')}</span>
                    <span className="core-pe-band__sector-pe-sep">·</span>
                    <span className="core-pe-band__sector-pe-value">{item.label}</span>
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </CoreCard>
  );
}
