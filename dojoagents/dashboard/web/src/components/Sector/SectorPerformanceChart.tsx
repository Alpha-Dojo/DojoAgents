import { useEffect, useMemo, useRef, useState, type MouseEvent as ReactMouseEvent } from 'react';
import { fetchBenchmarkCatalog } from '../../api/market';
import { useTranslation } from '../../hooks/useTranslation';
import type { BenchmarkCard } from '../../types/market';
import type { MarketCode } from '../../types/market';
import type { SectorLevelKey, SectorPerformancePoint } from '../../types/sector';
import type { ResolvedSectorPath } from '../../types/sectorTaxonomy';
import { scopeChartTitle } from '../../utils/sectorTitle';
import { DojoDropdownSelect } from '../ui';

interface SectorPerformanceChartProps {
  path: ResolvedSectorPath;
  scope: SectorLevelKey;
  points: SectorPerformancePoint[];
  windowStart?: string | null;
  windowEnd?: string | null;
  loading?: boolean;
}

type ChartSeriesKey = MarketCode | 'benchmark';

interface ChartPoint {
  date: string;
  us?: number | null;
  cn?: number | null;
  hk?: number | null;
  benchmark?: number | null;
}

const MARKET_OPTIONS: MarketCode[] = ['us', 'cn', 'hk'];

const MARKET_CLASS: Record<MarketCode, string> = {
  us: 'us',
  cn: 'cn',
  hk: 'hk',
};

const MARKET_LABEL: Record<MarketCode, string> = {
  us: 'US',
  cn: 'CN',
  hk: 'HK',
};

function forwardFillSeries(points: ChartPoint[], keys: ChartSeriesKey[]): ChartPoint[] {
  const last: Partial<Record<ChartSeriesKey, number>> = {};
  return points.map((point) => {
    const row: ChartPoint = { date: point.date };
    for (const key of keys) {
      const value = point[key];
      if (value != null && !Number.isNaN(value)) {
        last[key] = value;
      }
      if (last[key] != null) {
        row[key] = last[key];
      }
    }
    return row;
  });
}

function buildPath(values: Array<number | null | undefined>, width: number, height: number, min: number, max: number) {
  const span = max - min || 1;
  let path = '';

  values.forEach((value, index) => {
    if (value == null || Number.isNaN(value)) {
      return;
    }
    const x = (index / Math.max(values.length - 1, 1)) * width;
    const y = height - ((value - min) / span) * height;
    path += `${index === 0 || path === '' ? 'M' : 'L'}${x.toFixed(2)},${y.toFixed(2)}`;
  });

  return path;
}

function rebaseSeries(points: SectorPerformancePoint[], markets: MarketCode[]): ChartPoint[] {
  if (points.length === 0) return [];

  const baseValues: Partial<Record<MarketCode, number>> = {};
  for (const market of markets) {
    for (const point of points) {
      const value = point[market];
      if (value != null && value > 0) {
        baseValues[market] = value;
        break;
      }
    }
  }

  return points.map((point) => {
    const row: ChartPoint = { date: point.date };
    for (const market of markets) {
      const base = baseValues[market];
      const value = point[market];
      if (base != null && value != null && base > 0) {
        row[market] = Number(((value / base) * 100).toFixed(2));
      }
    }
    return row;
  });
}

function attachBenchmarkSeries(points: ChartPoint[], benchmark: BenchmarkCard | null): ChartPoint[] {
  if (!benchmark?.kline?.length || points.length === 0) {
    return points;
  }

  const closeByDate = new Map(
    benchmark.kline.map((bar) => [bar.datetime.slice(0, 10), bar.close]),
  );
  const sortedDates = [...closeByDate.keys()].sort();
  const t0Date = points[0].date;

  let baseClose: number | null = null;
  for (const date of sortedDates) {
    if (date <= t0Date) {
      baseClose = closeByDate.get(date) ?? baseClose;
    }
  }
  if (baseClose == null || baseClose <= 0) {
    return points;
  }

  let lastBenchmark: number | null = null;
  return points.map((point) => {
    const close = closeByDate.get(point.date);
    if (close != null && close > 0) {
      lastBenchmark = Number(((close / baseClose) * 100).toFixed(2));
    }
    return {
      ...point,
      benchmark: lastBenchmark,
    };
  });
}

function flattenBenchmarkOptions(
  catalog: Awaited<ReturnType<typeof fetchBenchmarkCatalog>> | null,
): BenchmarkCard[] {
  if (!catalog?.markets) return [];
  const seen = new Set<string>();
  const items: BenchmarkCard[] = [];
  for (const market of MARKET_OPTIONS) {
    for (const card of catalog.markets[market]?.benchmarks ?? []) {
      if (!card.kline?.length || seen.has(card.symbol)) continue;
      seen.add(card.symbol);
      items.push(card);
    }
  }
  return items;
}

function formatReturnPercent(indexValue: number): string {
  const pct = indexValue - 100;
  const sign = pct >= 0 ? '+' : '';
  return `${sign}${pct.toFixed(2)}%`;
}

function ChevronIcon() {
  return (
    <svg className="sphere-performance__chevron" viewBox="0 0 24 24" width="12" height="12" aria-hidden>
      <path
        d="M6 9l6 6 6-6"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function SectorPerformanceChart({
  path,
  scope,
  points,
  windowStart,
  windowEnd,
  loading = false,
}: SectorPerformanceChartProps) {
  const { locale, t } = useTranslation();
  const [selectedMarkets, setSelectedMarkets] = useState<MarketCode[]>([...MARKET_OPTIONS]);
  const [benchmarkSymbol, setBenchmarkSymbol] = useState('');
  const [marketsOpen, setMarketsOpen] = useState(false);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const [benchmarkCatalog, setBenchmarkCatalog] = useState<Awaited<ReturnType<typeof fetchBenchmarkCatalog>> | null>(
    null,
  );
  const marketsRef = useRef<HTMLDivElement>(null);
  const chartWrapRef = useRef<HTMLDivElement>(null);

  const chartTitle = useMemo(() => scopeChartTitle(path, scope, locale), [path, scope, locale]);

  useEffect(() => {
    let cancelled = false;
    fetchBenchmarkCatalog()
      .then((data) => {
        if (!cancelled) setBenchmarkCatalog(data);
      })
      .catch(() => {
        if (!cancelled) setBenchmarkCatalog(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const handlePointerDown = (event: MouseEvent) => {
      if (!marketsRef.current?.contains(event.target as Node)) {
        setMarketsOpen(false);
      }
    };
    window.addEventListener('mousedown', handlePointerDown);
    return () => window.removeEventListener('mousedown', handlePointerDown);
  }, []);

  const benchmarkOptions = useMemo(() => flattenBenchmarkOptions(benchmarkCatalog), [benchmarkCatalog]);
  const selectedBenchmark = useMemo(
    () => benchmarkOptions.find((item) => item.symbol === benchmarkSymbol) ?? null,
    [benchmarkOptions, benchmarkSymbol],
  );

  const toggleMarket = (market: MarketCode) => {
    setSelectedMarkets((prev) => {
      if (prev.includes(market)) {
        if (prev.length === 1) return prev;
        return prev.filter((item) => item !== market);
      }
      return [...prev, market];
    });
  };

  const seriesKeys = useMemo(() => {
    const keys: ChartSeriesKey[] = [...selectedMarkets];
    if (selectedBenchmark) keys.push('benchmark');
    return keys;
  }, [selectedMarkets, selectedBenchmark]);

  const displayPoints = useMemo(() => {
    const rebased = rebaseSeries(points, selectedMarkets);
    const withBenchmark = attachBenchmarkSeries(rebased, selectedBenchmark);
    return forwardFillSeries(withBenchmark, seriesKeys);
  }, [points, selectedMarkets, selectedBenchmark, seriesKeys]);

  const chart = useMemo(() => {
    const width = 520;
    const height = 180;
    const values = seriesKeys.flatMap((key) =>
      displayPoints.map((point) => point[key]).filter((value): value is number => value != null),
    );
    const min = values.length > 0 ? Math.min(...values) - 2 : 98;
    const max = values.length > 0 ? Math.max(...values) + 2 : 102;

    const paths = Object.fromEntries(
      seriesKeys.map((key) => [
        key,
        buildPath(
          displayPoints.map((point) => point[key]),
          width,
          height,
          min,
          max,
        ),
      ]),
    ) as Record<ChartSeriesKey, string>;

    return {
      width,
      height,
      min,
      max,
      paths,
      startDate: windowStart || displayPoints[0]?.date || '',
      endDate: windowEnd || displayPoints[displayPoints.length - 1]?.date || '',
      hasData: values.length > 0,
    };
  }, [displayPoints, seriesKeys, windowStart, windowEnd]);

  const activeIndex = hoverIndex;
  const activePoint = activeIndex != null ? displayPoints[activeIndex] : null;
  const crosshairX =
    activeIndex != null && displayPoints.length > 1
      ? (activeIndex / (displayPoints.length - 1)) * chart.width
      : null;

  const handleChartMouseMove = (event: ReactMouseEvent<HTMLDivElement>) => {
    if (!chartWrapRef.current || displayPoints.length === 0) return;
    const rect = chartWrapRef.current.getBoundingClientRect();
    const ratio = Math.min(Math.max((event.clientX - rect.left) / rect.width, 0), 1);
    const index = Math.round(ratio * Math.max(displayPoints.length - 1, 0));
    setHoverIndex(index);
  };

  const handleChartMouseLeave = () => {
    setHoverIndex(null);
  };

  const marketsLabel = selectedMarkets.map((market) => MARKET_LABEL[market]).join(' · ');
  const benchmarkLabel = selectedBenchmark
    ? locale === 'zh'
      ? selectedBenchmark.name.zh || selectedBenchmark.name.en
      : selectedBenchmark.name.en || selectedBenchmark.name.zh
    : t('sectorPage.benchmarkNone');

  return (
    <article className="sphere-card sphere-performance">
      <div className="sphere-performance__head">
        <h3 className="sphere-card__title sphere-card__title--compact sphere-performance__title">{chartTitle}</h3>
        <div className="sphere-performance__controls">
          <div className="sphere-performance__legend sphere-performance__legend--head">
            {selectedMarkets.map((market) => (
              <span
                key={market}
                className={`sphere-performance__legend-item sphere-performance__legend-item--${MARKET_CLASS[market]}`}
              >
                {MARKET_LABEL[market]}
              </span>
            ))}
            {selectedBenchmark && (
              <span className="sphere-performance__legend-item sphere-performance__legend-item--benchmark">
                {benchmarkLabel}
              </span>
            )}
          </div>
          <div className="sphere-performance__markets" ref={marketsRef}>
            <button
              type="button"
              className={`sphere-performance__markets-trigger ${marketsOpen ? 'sphere-performance__markets-trigger--open' : ''}`}
              aria-haspopup="listbox"
              aria-expanded={marketsOpen}
              aria-label={t('sectorPage.marketsLabel')}
              onClick={() => setMarketsOpen((prev) => !prev)}
            >
              <span>{marketsLabel}</span>
              <ChevronIcon />
            </button>
            {marketsOpen && (
              <ul className="sphere-performance__markets-menu" role="listbox" aria-label={t('sectorPage.marketsLabel')}>
                {MARKET_OPTIONS.map((market) => {
                  const checked = selectedMarkets.includes(market);
                  return (
                    <li key={market} role="presentation">
                      <button
                        type="button"
                        role="option"
                        aria-selected={checked}
                        className={`sphere-performance__markets-option sphere-performance__markets-option--${MARKET_CLASS[market]} ${checked ? 'sphere-performance__markets-option--active' : ''}`}
                        onClick={() => toggleMarket(market)}
                      >
                        <span className="sphere-performance__markets-check" aria-hidden>
                          {checked ? '✓' : ''}
                        </span>
                        {MARKET_LABEL[market]}
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
          <div className="sphere-performance__markets">
            <DojoDropdownSelect
              aria-label={t('sectorPage.benchmarkLabel')}
              className="sphere-performance__benchmark-select"
              value={benchmarkSymbol}
              onChange={setBenchmarkSymbol}
              dropdownMinWidth={180}
              options={[
                { value: '', label: t('sectorPage.benchmarkNone') },
                ...benchmarkOptions.map((item) => ({
                  value: item.symbol,
                  label: locale === 'zh' ? item.name.zh || item.name.en : item.name.en || item.name.zh,
                })),
              ]}
            />
          </div>
        </div>
      </div>
      <div
        ref={chartWrapRef}
        className="sphere-performance__chart-wrap"
        onMouseMove={handleChartMouseMove}
        onMouseLeave={handleChartMouseLeave}
      >
        {loading ? (
          <p className="sphere-performance__status">{t('sectorPage.loadingPerformance')}</p>
        ) : !chart.hasData ? (
          <p className="sphere-performance__status">{t('sectorPage.noPerformanceData')}</p>
        ) : (
          <>
            <svg
              className="sphere-performance__chart"
              viewBox={`0 0 ${chart.width} ${chart.height}`}
              preserveAspectRatio="none"
              aria-hidden
            >
              {crosshairX != null && hoverIndex != null && (
                <line
                  x1={crosshairX}
                  y1={0}
                  x2={crosshairX}
                  y2={chart.height}
                  className="sphere-performance__crosshair"
                />
              )}
              {selectedMarkets.map((market) => (
                <path
                  key={market}
                  d={chart.paths[market]}
                  className={`sphere-performance__line sphere-performance__line--${MARKET_CLASS[market]}`}
                />
              ))}
              {selectedBenchmark && chart.paths.benchmark && (
                <path
                  d={chart.paths.benchmark}
                  className="sphere-performance__line sphere-performance__line--benchmark"
                />
              )}
              {activeIndex != null &&
                seriesKeys.map((key) => {
                  const value = displayPoints[activeIndex]?.[key];
                  if (value == null) return null;
                  const span = chart.max - chart.min || 1;
                  const x = (activeIndex / Math.max(displayPoints.length - 1, 1)) * chart.width;
                  const y = chart.height - ((value - chart.min) / span) * chart.height;
                  const dotClass =
                    key === 'benchmark' ? 'benchmark' : MARKET_CLASS[key as MarketCode];
                  return (
                    <circle
                      key={key}
                      cx={x}
                      cy={y}
                      r={3.2}
                      className={`sphere-performance__dot sphere-performance__dot--${dotClass}`}
                    />
                  );
                })}
            </svg>
            {activePoint && hoverIndex != null && (
              <div className="sphere-performance__tooltip">
                <div className="sphere-performance__tooltip-date">{activePoint.date}</div>
                <div className="sphere-performance__tooltip-rows">
                  {selectedMarkets.map((market) => {
                    const value = activePoint[market];
                    if (value == null) return null;
                    const direction = value >= 100 ? 'up' : 'down';
                    return (
                      <div
                        key={market}
                        className={`sphere-performance__tooltip-row sphere-performance__tooltip-row--${MARKET_CLASS[market]}`}
                      >
                        <span className="sphere-performance__tooltip-label">{MARKET_LABEL[market]}</span>
                        <span className={`sphere-performance__tooltip-value sphere-performance__tooltip-value--${direction}`}>
                          {formatReturnPercent(value)}
                        </span>
                      </div>
                    );
                  })}
                  {selectedBenchmark && activePoint.benchmark != null && (
                    <div className="sphere-performance__tooltip-row sphere-performance__tooltip-row--benchmark">
                      <span className="sphere-performance__tooltip-label">{benchmarkLabel}</span>
                      <span
                        className={`sphere-performance__tooltip-value sphere-performance__tooltip-value--${
                          activePoint.benchmark >= 100 ? 'up' : 'down'
                        }`}
                      >
                        {formatReturnPercent(activePoint.benchmark)}
                      </span>
                    </div>
                  )}
                </div>
              </div>
            )}
          </>
        )}
      </div>
      <div className="sphere-performance__foot">
        <span className="sphere-performance__axis-date">{chart.startDate}</span>
        <span className={`sphere-performance__axis-date sphere-performance__axis-date--active ${hoverIndex != null ? 'sphere-performance__axis-date--visible' : ''}`}>
          {activePoint?.date ?? ''}
        </span>
        <span className="sphere-performance__axis-date">{chart.endDate}</span>
      </div>
    </article>
  );
}
