import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import type { BenchmarkCard, BenchmarkKlinePoint } from '../../types/market';
import { formatKlineAxisDate, findKlineIndexForDate, resolveKlineBarDate, sliceKlineToWindow } from '../../utils/klineDate';
import { DojoDropdownSelect } from '../ui';

interface SparklineProps {
  kline: BenchmarkKlinePoint[];
  positive: boolean;
  id: string;
  currentPrice: number;
  changePercent: number;
  benchmarks: BenchmarkCard[];
  symbol: string;
  onSymbolChange: (symbol: string) => void;
  windowStart?: string;
  windowEnd?: string;
  linkedHoverDate?: string | null;
  onLinkedHoverDateChange?: (date: string | null) => void;
}

const MIN_VISIBLE_BARS = 12;
const W = 400;
const H = 64;
const PAD_X = 8;
const PAD_Y = 8;

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function formatPrice(value: number): string {
  return value.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function formatPercent(value: number): string {
  const sign = value > 0 ? '+' : value < 0 ? '' : '';
  return `${sign}${value.toFixed(2)}%`;
}

function indexAtRatio(viewStart: number, viewEnd: number, ratio: number): number {
  return Math.round(viewStart + ratio * (viewEnd - viewStart));
}

function isMovingToLinkedChartPlot(relatedTarget: EventTarget | null): boolean {
  if (!(relatedTarget instanceof Node)) return false;
  const el = relatedTarget instanceof Element ? relatedTarget : relatedTarget.parentElement;
  return Boolean(el?.closest('.market-hero__chart'));
}

export function Sparkline({
  kline,
  positive,
  id,
  currentPrice,
  changePercent,
  benchmarks,
  symbol,
  onSymbolChange,
  windowStart,
  windowEnd,
  linkedHoverDate = null,
  onLinkedHoverDateChange,
}: SparklineProps) {
  const { text } = useTranslation();
  const chartRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{ startX: number; viewStart: number; viewEnd: number } | null>(null);

  const displayKline = useMemo(() => {
    if (!windowStart || !windowEnd) return kline;
    return sliceKlineToWindow(kline, windowStart, windowEnd);
  }, [kline, windowStart, windowEnd]);

  const [viewStart, setViewStart] = useState(0);
  const [viewEnd, setViewEnd] = useState(() => Math.max(0, displayKline.length - 1));
  const [dragging, setDragging] = useState(false);

  const totalBars = displayKline.length;

  useEffect(() => {
    setViewStart(0);
    setViewEnd(Math.max(0, totalBars - 1));
  }, [symbol, totalBars, windowStart, windowEnd]);

  const windowSize = viewEnd - viewStart + 1;
  const isZoomed = windowSize < totalBars;

  const applyViewport = useCallback(
    (start: number, end: number) => {
      const size = clamp(end - start + 1, MIN_VISIBLE_BARS, totalBars);
      let nextStart = clamp(start, 0, totalBars - size);
      let nextEnd = nextStart + size - 1;
      if (nextEnd >= totalBars) {
        nextEnd = totalBars - 1;
        nextStart = nextEnd - size + 1;
      }
      setViewStart(nextStart);
      setViewEnd(nextEnd);
    },
    [totalBars],
  );

  const pickGlobalIndex = useCallback(
    (clientX: number, rect: DOMRect) => {
      if (totalBars < 2 || viewEnd <= viewStart) return viewStart;
      const ratio = clamp((clientX - rect.left) / rect.width, 0, 1);
      return indexAtRatio(viewStart, viewEnd, ratio);
    },
    [totalBars, viewEnd, viewStart],
  );

  const handleMouseMove = useCallback(
    (event: React.MouseEvent<HTMLDivElement>) => {
      if (dragging) return;
      const rect = event.currentTarget.getBoundingClientRect();
      const index = pickGlobalIndex(event.clientX, rect);
      onLinkedHoverDateChange?.(resolveKlineBarDate(displayKline, index));
    },
    [dragging, displayKline, onLinkedHoverDateChange, pickGlobalIndex],
  );

  const handleMouseLeave = useCallback(
    (event: React.MouseEvent<HTMLDivElement>) => {
      if (dragging || isMovingToLinkedChartPlot(event.relatedTarget)) return;
      onLinkedHoverDateChange?.(null);
    },
    [dragging, onLinkedHoverDateChange],
  );

  const handleMouseDown = useCallback(
    (event: React.MouseEvent<HTMLDivElement>) => {
      if (event.button !== 0 || totalBars < 2) return;
      event.preventDefault();
      dragRef.current = {
        startX: event.clientX,
        viewStart,
        viewEnd,
      };
      setDragging(true);
      onLinkedHoverDateChange?.(null);
    },
    [onLinkedHoverDateChange, totalBars, viewEnd, viewStart],
  );

  useEffect(() => {
    if (!dragging) return;

    const handleMove = (event: MouseEvent) => {
      const drag = dragRef.current;
      const el = chartRef.current;
      if (!drag || !el) return;

      const rect = el.getBoundingClientRect();
      const dx = event.clientX - drag.startX;
      const shift = Math.round((dx / rect.width) * windowSize);
      applyViewport(drag.viewStart - shift, drag.viewEnd - shift);
    };

    const handleUp = () => {
      dragRef.current = null;
      setDragging(false);
    };

    window.addEventListener('mousemove', handleMove);
    window.addEventListener('mouseup', handleUp);
    return () => {
      window.removeEventListener('mousemove', handleMove);
      window.removeEventListener('mouseup', handleUp);
    };
  }, [applyViewport, dragging, windowSize]);

  useEffect(() => {
    const el = chartRef.current;
    if (!el || totalBars < MIN_VISIBLE_BARS) return;

    const handleWheel = (event: WheelEvent) => {
      event.preventDefault();
      const rect = el.getBoundingClientRect();
      const ratio = clamp((event.clientX - rect.left) / rect.width, 0, 1);
      const anchor = indexAtRatio(viewStart, viewEnd, ratio);
      const factor = Math.exp(event.deltaY * 0.003);
      const nextSize = clamp(Math.round(windowSize * factor), MIN_VISIBLE_BARS, totalBars);
      const nextStart = clamp(
        Math.round(anchor - ratio * (nextSize - 1)),
        0,
        totalBars - nextSize,
      );
      applyViewport(nextStart, nextStart + nextSize - 1);
    };

    el.addEventListener('wheel', handleWheel, { passive: false });
    return () => el.removeEventListener('wheel', handleWheel);
  }, [applyViewport, totalBars, viewEnd, viewStart, windowSize]);

  const visibleIndices = useMemo(() => {
    if (totalBars < 2) return [];
    return Array.from({ length: viewEnd - viewStart + 1 }, (_, i) => viewStart + i);
  }, [totalBars, viewEnd, viewStart]);

  const visibleCloses = useMemo(
    () => visibleIndices.map((i) => displayKline[i].close),
    [displayKline, visibleIndices],
  );

  if (totalBars < 2) return null;

  const min = Math.min(...visibleCloses);
  const max = Math.max(...visibleCloses);
  const range = max - min || 1;

  const coords = visibleCloses.map((p, i) => {
    const x = PAD_X + (i / (visibleCloses.length - 1)) * (W - PAD_X * 2);
    const y = PAD_Y + (1 - (p - min) / range) * (H - PAD_Y * 2);
    return { x, y, globalIndex: visibleIndices[i] };
  });

  const linePoints = coords.map((c) => `${c.x},${c.y}`).join(' ');
  const areaPoints = [
    `${coords[0].x},${H - PAD_Y}`,
    ...coords.map((c) => `${c.x},${c.y}`),
    `${coords[coords.length - 1].x},${H - PAD_Y}`,
  ].join(' ');

  const gradId = `spark-fill-${id}`;

  const isLinkedHovering = linkedHoverDate !== null && !dragging;
  const activeGlobalIndex = isLinkedHovering
    ? findKlineIndexForDate(displayKline, linkedHoverDate)
    : totalBars - 1;
  const isHovering = isLinkedHovering;
  const activeLocal = coords.findIndex((c) => c.globalIndex === activeGlobalIndex);
  const active = activeLocal >= 0 ? coords[activeLocal] : null;
  const activeBar = displayKline[activeGlobalIndex];
  const activeBarDate = resolveKlineBarDate(displayKline, activeGlobalIndex);
  const prevBar = activeGlobalIndex > 0 ? displayKline[activeGlobalIndex - 1] : null;

  const displayPrice = isHovering ? activeBar.close : currentPrice;
  const displayChange = isHovering
    ? prevBar && prevBar.close !== 0
      ? ((activeBar.close - prevBar.close) / prevBar.close) * 100
      : 0
    : changePercent;
  const displayChangeUp = displayChange >= 0;
  const stroke = positive ? 'var(--green)' : 'var(--red)';

  const axisStartIndex = visibleIndices[0];
  const axisEndIndex = visibleIndices[visibleIndices.length - 1];
  const axisMidIndex = visibleIndices[Math.floor((visibleIndices.length - 1) / 2)];
  const axisStartDate = windowStart ?? resolveKlineBarDate(displayKline, axisStartIndex);
  const axisEndDate = windowEnd ?? resolveKlineBarDate(displayKline, axisEndIndex);
  const startYear = axisStartDate.slice(0, 4);
  const endYear = axisEndDate.slice(0, 4);
  const spanYears = startYear !== endYear;

  const axisTicks = [
    { date: axisStartDate, align: 'start' as const, local: 0 },
    ...(visibleIndices.length > 2
      ? [{
          date: resolveKlineBarDate(displayKline, axisMidIndex),
          align: 'center' as const,
          local: Math.floor((coords.length - 1) / 2),
        }]
      : []),
    { date: axisEndDate, align: 'end' as const, local: coords.length - 1 },
  ];

  return (
    <div
      className={`market-hero__chart-wrap${isHovering ? ' market-hero__chart-wrap--hover' : ''}${
        isZoomed ? ' market-hero__chart-wrap--zoomed' : ''
      }`}
    >
      <div
        className={`market-hero__chart-head${isHovering ? ' market-hero__chart-head--hover' : ''}`}
        aria-live="polite"
      >
        <DojoDropdownSelect
          aria-label="切换指数"
          className="market-hero__chart-head-select"
          dropdownMinWidth={132}
          value={symbol}
          onChange={onSymbolChange}
          options={benchmarks.map((benchmark) => ({
            value: benchmark.symbol,
            label: text(benchmark.name),
          }))}
        />

        <div className="market-hero__chart-head-quote">
          {isHovering && activeBarDate && (
            <time className="market-hero__chart-head-date" dateTime={activeBarDate}>
              {activeBarDate}
            </time>
          )}
          <span
            className={`market-hero__chart-head-price market-hero__chart-head-price--${
              displayChangeUp ? 'up' : 'down'
            }`}
          >
            {formatPrice(displayPrice)}
          </span>
          <span
            className={`market-hero__chart-head-chg market-hero__chart-head-chg--${
              displayChangeUp ? 'up' : 'down'
            }`}
          >
            {formatPercent(displayChange)}
          </span>
        </div>
      </div>

      <div
        ref={chartRef}
        className={`market-hero__chart${dragging ? ' market-hero__chart--dragging' : ''}`}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
        role="img"
        aria-label={`指数走势，${axisStartDate} 至 ${axisEndDate}`}
      >
        <svg className="market-hero__sparkline" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
          <defs>
            <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={stroke} stopOpacity="0.28" />
              <stop offset="100%" stopColor={stroke} stopOpacity="0" />
            </linearGradient>
          </defs>
          {axisTicks.map(({ local, date }) => (
            <line
              key={`grid-${date}-${local}`}
              x1={coords[local].x}
              x2={coords[local].x}
              y1={PAD_Y}
              y2={H - PAD_Y}
              stroke="var(--border-dim)"
              strokeWidth="1"
              vectorEffect="non-scaling-stroke"
              opacity={isHovering && activeBarDate === date ? 0 : 0.35}
            />
          ))}
          <polygon points={areaPoints} fill={`url(#${gradId})`} />
          <polyline
            fill="none"
            stroke={stroke}
            strokeWidth="2"
            strokeLinejoin="round"
            strokeLinecap="round"
            vectorEffect="non-scaling-stroke"
            points={linePoints}
          />
          {isHovering && active && (
            <>
              <line
                x1={active.x}
                x2={active.x}
                y1={PAD_Y}
                y2={H - PAD_Y}
                className="market-hero__crosshair-v"
              />
              <circle
                cx={active.x}
                cy={active.y}
                r="3.5"
                className="market-hero__hover-dot"
              />
            </>
          )}
        </svg>
      </div>

      <div className="market-hero__chart-axis" aria-hidden>
        {axisTicks.map(({ date, align }) => (
          <span
            key={date}
            className={`market-hero__chart-axis-tick market-hero__chart-axis-tick--${align}${
              isHovering && activeBarDate === date ? ' market-hero__chart-axis-tick--active' : ''
            }`}
          >
            {formatKlineAxisDate(date, spanYears)}
          </span>
        ))}
      </div>
    </div>
  );
}
