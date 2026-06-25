import type { ReactNode } from 'react';
import type { AgentVizBlock } from '../../../types/agentViz';
import { buildDonutPaths } from '../../../utils/coreIncomeDistribution';
import { buildSparklinePath } from '../../../utils/folioFormat';
import {
  buildAgentNavReturnAxisTicks,
  prepareAgentLineChart,
  prepareAgentPortfolioNavChart,
} from '../../../utils/agentVizLineChart';
import {
  formatVizCell,
  formatVizCompactAmount,
  formatVizNumber,
  formatVizPercent,
  percentTone,
} from '../../../utils/agentVizFormat';
import {
  agentMarketLineColor,
  agentMarketSliceColor,
  normalizeAgentMarket,
} from '../../../utils/agentVizMarket';
import type {
  AgentVizDonutSlice,
  AgentVizKlineBar,
  AgentVizKpiItem,
  AgentVizLineSeries,
  AgentVizMarketKpiGroup,
  AgentVizRankItem,
  AgentVizTableColumn,
  AgentVizTableGroup,
  AgentVizTimelineItem,
} from '../../../types/agentViz';
import { formatMarketCap } from '../../../utils/marketStats';
import { useTranslation } from '../../../hooks/useTranslation';
import { localizeAgentVizBlocks } from '../../../utils/agentVizI18n';
import {
  barDirection,
  buildAgentPriceKlineLayout,
  candleGeometry,
} from '../../../utils/agentPriceKlineChart';
import { AgentMarketBadge } from './AgentMarketBadge';
import './AgentVizPanel.css';

function blockMarket(block: AgentVizBlock): string | null {
  return normalizeAgentMarket(block.payload.market) ?? null;
}

function BlockShell({
  block,
  children,
}: {
  block: AgentVizBlock;
  children: ReactNode;
}) {
  const market = blockMarket(block);
  return (
    <article
      className={`agent-viz-block${market ? ` agent-viz-block--${market}` : ''}`}
      data-kind={block.kind}
      data-market={market ?? undefined}
    >
      <header className="agent-viz-block__head">
        <div className="agent-viz-block__headline">
          {market ? <AgentMarketBadge market={market} compact /> : null}
          {block.title ? <h4 className="agent-viz-block__title">{block.title}</h4> : null}
        </div>
        {block.subtitle ? <p className="agent-viz-block__subtitle">{block.subtitle}</p> : null}
      </header>
      <div className="agent-viz-block__body">{children}</div>
      {block.truncated ? <p className="agent-viz-block__truncated">…</p> : null}
    </article>
  );
}

function formatKpiValue(item: AgentVizKpiItem): string {
  if (item.value == null || item.value === '') return '—';
  if (item.value_format) {
    return formatVizCell(item.value, item.value_format);
  }
  if (item.key === 'netValue') {
    return formatVizCompactAmount(item.value);
  }
  if (item.key === 'listed_count') {
    const num = typeof item.value === 'number' ? item.value : Number(item.value);
    return Number.isFinite(num) ? String(Math.round(num)) : String(item.value);
  }
  return String(item.value);
}

function renderKpiItem(item: AgentVizKpiItem) {
  const tone = item.tone ?? 'neutral';
  const displayValue = formatKpiValue(item);
  return (
    <div key={item.key ?? item.label} className={`agent-viz-kpi__item agent-viz-kpi__item--${tone}`}>
      <span className="agent-viz-kpi__label">{item.label}</span>
      <span className="agent-viz-kpi__value">{displayValue}</span>
      {item.meta ? <span className="agent-viz-kpi__meta">{item.meta}</span> : null}
      {item.delta ? <span className="agent-viz-kpi__delta">{item.delta}</span> : null}
    </div>
  );
}

function KpiRowBlock({ block }: { block: AgentVizBlock }) {
  const layout = block.payload.layout as string | undefined;
  const marketGroups = (block.payload.markets as AgentVizMarketKpiGroup[] | undefined) ?? [];
  const flatItems = (block.payload.items as AgentVizKpiItem[] | undefined) ?? [];

  if (layout === 'by_market' && marketGroups.length > 0) {
    return (
      <BlockShell block={block}>
        <div className="agent-viz-kpi-stack">
          {marketGroups.map((group) => {
            const market = normalizeAgentMarket(group.market);
            if (!market) return null;
            return (
              <section key={market} className={`agent-viz-kpi-row agent-viz-kpi-row--${market}`}>
                <AgentMarketBadge market={market} />
                <div className="agent-viz-kpi agent-viz-kpi--market-grid">
                  {group.items.map(renderKpiItem)}
                </div>
              </section>
            );
          })}
        </div>
      </BlockShell>
    );
  }

  if (!flatItems.length) return null;
  return (
    <BlockShell block={block}>
      <div className="agent-viz-kpi">{flatItems.map(renderKpiItem)}</div>
    </BlockShell>
  );
}

function QuoteCardBlock({ block }: { block: AgentVizBlock }) {
  const { t } = useTranslation();
  const p = block.payload;
  const change = p.change_percent as number | undefined;
  const tone = percentTone(change);
  const name = (p.name_zh as string) || (p.name_en as string) || '';
  const market = normalizeAgentMarket(p.market);
  return (
    <BlockShell block={block}>
      <div className={`agent-viz-quote${market ? ` agent-viz-quote--${market}` : ''}`}>
        <div className="agent-viz-quote__head">
          <span className="agent-viz-quote__name">{name}</span>
          <span className="agent-viz-quote__ticker">{String(p.ticker ?? '')}</span>
        </div>
        <div className="agent-viz-quote__price-row">
          <span className="agent-viz-quote__price">{formatVizCompactAmount(p.last_price)}</span>
          <span className={`agent-viz-quote__chg agent-viz-quote__chg--${tone}`}>
            {formatVizPercent(change)}
          </span>
        </div>
        <div className="agent-viz-quote__grid">
          <span>PE {formatVizNumber(p.pe)}</span>
          <span>PB {formatVizNumber(p.pb)}</span>
          <span>
            {t('agentViz.quote.cap')} {formatMarketCap(Number(p.market_cap))}
          </span>
          <span>
            {t('agentViz.quote.highLow')} {formatVizNumber(p.high)} / {formatVizNumber(p.low)}
          </span>
        </div>
      </div>
    </BlockShell>
  );
}

function TableRows({
  columns,
  rows,
}: {
  columns: AgentVizTableColumn[];
  rows: Record<string, unknown>[];
}) {
  return (
    <table className="agent-viz-table">
      <thead>
        <tr>
          {columns.map((col) => (
            <th key={col.key}>{col.label}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, index) => (
          <tr key={`${index}-${String(row.ticker ?? row.name ?? index)}`}>
            {columns.map((col) => {
              const raw = row[col.key];
              const tone = col.format === 'percent' ? percentTone(raw) : ('flat' as const);
              return (
                <td
                  key={col.key}
                  className={
                    col.format === 'percent'
                      ? `agent-viz-table__pct agent-viz-table__pct--${tone}`
                      : undefined
                  }
                >
                  {formatVizCell(raw, col.format)}
                </td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function TableBlock({ block }: { block: AgentVizBlock }) {
  const columns = (block.payload.columns as AgentVizTableColumn[] | undefined) ?? [];
  const layout = block.payload.layout as string | undefined;
  const groups = (block.payload.groups as AgentVizTableGroup[] | undefined) ?? [];
  const rows = (block.payload.rows as Record<string, unknown>[] | undefined) ?? [];
  if (!columns.length) return null;

  if (layout === 'by_market' && groups.length > 0) {
    return (
      <BlockShell block={block}>
        <div className="agent-viz-table-groups">
          {groups.map((group) => {
            const market = normalizeAgentMarket(group.market);
            if (!market || !group.rows.length) return null;
            return (
              <section key={market} className={`agent-viz-table-group agent-viz-table-group--${market}`}>
                <AgentMarketBadge market={market} />
                <div className="agent-viz-table-wrap">
                  <TableRows columns={columns} rows={group.rows} />
                </div>
              </section>
            );
          })}
        </div>
      </BlockShell>
    );
  }

  if (!rows.length) return null;
  return (
    <BlockShell block={block}>
      <div className="agent-viz-table-wrap">
        <TableRows columns={columns} rows={rows} />
      </div>
    </BlockShell>
  );
}

function SparklineBlock({ block }: { block: AgentVizBlock }) {
  const points = (block.payload.points as { value?: number }[] | undefined) ?? [];
  const values = points
    .map((pt) => pt.value)
    .filter((v): v is number => typeof v === 'number');
  const path = buildSparklinePath(values, 280, 56);
  const tone = percentTone(block.payload.change_percent);
  const market = normalizeAgentMarket(block.payload.market);
  const stroke = market ? agentMarketLineColor(market) : undefined;
  if (!path) return null;
  return (
    <BlockShell block={block}>
      <div className="agent-viz-sparkline">
        <div className="agent-viz-sparkline__meta">
          <span className="agent-viz-sparkline__price">{formatVizCompactAmount(block.payload.price)}</span>
          <span className={`agent-viz-sparkline__chg agent-viz-sparkline__chg--${tone}`}>
            {formatVizPercent(block.payload.change_percent)}
          </span>
        </div>
        <svg viewBox="0 0 280 56" className="agent-viz-sparkline__chart" role="img">
          <path
            d={path}
            className={`agent-viz-sparkline__path agent-viz-sparkline__path--${tone}`}
            style={stroke ? { stroke } : undefined}
          />
        </svg>
      </div>
    </BlockShell>
  );
}

function PortfolioNavLineBlock({ block, series }: { block: AgentVizBlock; series: AgentVizLineSeries[] }) {
  const CHART_W = 280;
  const CHART_H = 120;
  const PAD_X = 6;
  const PAD_Y = 6;
  const Y_AXIS_W = 42;

  const chart = prepareAgentPortfolioNavChart(series, CHART_W, CHART_H, PAD_X, PAD_Y);
  if (!chart || chart.layers.length === 0) return null;

  const yAxisTicks = buildAgentNavReturnAxisTicks(chart.yMin, chart.yMax, CHART_H, PAD_Y, 4);
  const longest = chart.layers.reduce((best, layer) =>
    layer.points.length > best.points.length ? layer : best,
  );
  const startDate = longest.points[0]?.date;
  const endDate = longest.points[longest.points.length - 1]?.date;

  return (
    <BlockShell block={block}>
      <div className="agent-viz-line-stage">
        <div className="agent-viz-line__y-axis" style={{ width: Y_AXIS_W }} aria-hidden>
          {yAxisTicks.map((tick) => (
            <span
              key={tick.indexValue}
              className="agent-viz-line__y-tick"
              style={{ top: `${tick.topPct}%` }}
            >
              {tick.label}
            </span>
          ))}
        </div>
        <div className="agent-viz-line__plot">
          <svg
            viewBox={`0 0 ${CHART_W} ${CHART_H}`}
            className="agent-viz-line__svg"
            role="img"
            preserveAspectRatio="none"
          >
            {yAxisTicks.map((tick) => (
              <line
                key={`grid-${tick.indexValue}`}
                x1={PAD_X}
                y1={tick.y}
                x2={CHART_W - PAD_X}
                y2={tick.y}
                className="agent-viz-line__grid"
              />
            ))}
            {chart.layers.map((layer) => (
              <path
                key={layer.id}
                d={layer.path}
                fill="none"
                stroke={layer.color}
                strokeWidth={2.25}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            ))}
          </svg>
        </div>
      </div>
      {startDate && endDate && startDate !== endDate ? (
        <div className="agent-viz-line__axis" style={{ paddingLeft: Y_AXIS_W }}>
          <span className="agent-viz-line__axis-start">{startDate}</span>
          <span className="agent-viz-line__axis-end">{endDate}</span>
        </div>
      ) : null}
      <div className="agent-viz-line__legend">
        {chart.layers.map((layer) => (
          <span key={layer.id} className="agent-viz-line__legend-item">
            <i style={{ background: layer.color }} />
            {layer.label}
          </span>
        ))}
      </div>
    </BlockShell>
  );
}

function PriceKlineBlock({ block }: { block: AgentVizBlock }) {
  const rawBars = (block.payload.bars as AgentVizKlineBar[] | undefined) ?? [];
  const bars = rawBars.filter(
    (bar) =>
      bar &&
      typeof bar.date === 'string' &&
      [bar.open, bar.high, bar.low, bar.close].every((v) => typeof v === 'number' && Number.isFinite(v)),
  );
  const layout = buildAgentPriceKlineLayout(bars);
  if (!layout) return null;

  const startDate = bars[0]?.date;
  const endDate = bars[bars.length - 1]?.date;
  const market = normalizeAgentMarket(block.payload.market);

  return (
    <BlockShell block={block}>
      <div className="agent-viz-price-kline">
        <svg
          viewBox={`0 0 ${layout.width} ${layout.priceHeight}`}
          className="agent-viz-price-kline__price"
          role="img"
          aria-label={block.title}
          preserveAspectRatio="none"
        >
          <rect
            x={0}
            y={0}
            width={layout.width}
            height={layout.priceHeight}
            className="agent-viz-price-kline__bg"
          />
          {bars.map((bar, index) => {
            const geom = candleGeometry(bar, index, bars.length, layout);
            const direction = barDirection(bar);
            return (
              <g key={`${bar.date}-${index}`} shapeRendering="crispEdges">
                <line
                  x1={geom.cx}
                  x2={geom.cx}
                  y1={geom.highY}
                  y2={geom.lowY}
                  className={`agent-viz-price-kline__wick agent-viz-price-kline__wick--${direction}`}
                />
                <rect
                  x={geom.cx - geom.barW / 2}
                  y={geom.bodyTop}
                  width={geom.barW}
                  height={geom.bodyHeight}
                  className={`agent-viz-price-kline__body agent-viz-price-kline__body--${direction}`}
                />
              </g>
            );
          })}
        </svg>
        <svg
          viewBox={`0 0 ${layout.width} ${layout.volumeHeight}`}
          className="agent-viz-price-kline__volume"
          role="presentation"
          preserveAspectRatio="none"
        >
          {bars.map((bar, index) => {
            const geom = candleGeometry(bar, index, bars.length, layout);
            const direction = barDirection(bar);
            if (!geom.volumeHeight) return null;
            return (
              <rect
                key={`vol-${bar.date}-${index}`}
                x={geom.cx - geom.barW / 2}
                y={geom.volumeY}
                width={geom.barW}
                height={geom.volumeHeight}
                className={`agent-viz-price-kline__vol agent-viz-price-kline__vol--${direction}`}
              />
            );
          })}
        </svg>
      </div>
      {startDate && endDate ? (
        <div className="agent-viz-line__axis">
          <span>{startDate}</span>
          <span>{endDate}</span>
        </div>
      ) : null}
      {market ? (
        <div className="agent-viz-line__legend">
          <span className="agent-viz-line__legend-item">
            <i style={{ background: agentMarketLineColor(market) }} />
            {String(block.payload.ticker ?? block.title)}
          </span>
        </div>
      ) : null}
    </BlockShell>
  );
}

function LineBlock({ block }: { block: AgentVizBlock }) {
  const series = (block.payload.series as AgentVizLineSeries[] | undefined) ?? [];
  const benchmark = (block.payload.benchmark_series as AgentVizLineSeries[] | undefined) ?? [];
  const width = 320;
  const height = 120;
  const isPortfolioNav = block.source_tool === 'get_portfolio_analysis';

  if (isPortfolioNav) {
    return <PortfolioNavLineBlock block={block} series={series} />;
  }

  const prepared = prepareAgentLineChart(series, benchmark, width, height, {
    includeBenchmarks: true,
  });
  if (prepared.length === 0) return null;

  const startDate = prepared[0]?.points[0]?.date;
  const endDate = prepared[0]?.points[prepared[0].points.length - 1]?.date;

  return (
    <BlockShell block={block}>
      <svg viewBox={`0 0 ${width} ${height}`} className="agent-viz-line" role="img">
        {prepared.map((entry) => (
          <path
            key={entry.id}
            d={entry.path}
            fill="none"
            stroke={entry.color}
            strokeWidth={2.25}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        ))}
      </svg>
      <div className="agent-viz-line__legend">
        {prepared.map((entry) => (
          <span key={entry.id} className="agent-viz-line__legend-item">
            <i style={{ background: entry.color.replace(/66$|88$/, '') || entry.color }} />
            {entry.label}
          </span>
        ))}
      </div>
      {startDate && endDate && startDate !== endDate ? (
        <div className="agent-viz-line__axis">
          <span>{startDate}</span>
          <span>{endDate}</span>
        </div>
      ) : null}
    </BlockShell>
  );
}

function BarBlock({ block }: { block: AgentVizBlock }) {
  const categories = (block.payload.categories as string[] | undefined) ?? [];
  const series = (block.payload.series as { label: string; values: (number | null)[] }[] | undefined) ?? [];
  const market = normalizeAgentMarket(block.payload.market);
  if (!categories.length || !series.length) return null;
  const flat = series.flatMap((s) => s.values.filter((v): v is number => typeof v === 'number'));
  const max = Math.max(...flat, 1);
  return (
    <BlockShell block={block}>
      <div className="agent-viz-bar">
        {categories.map((cat, catIndex) => (
          <div key={cat} className="agent-viz-bar__group">
            <div className="agent-viz-bar__cols">
              {series.map((s, sIndex) => {
                const value = s.values[catIndex];
                const heightPct =
                  typeof value === 'number' && value > 0 ? Math.max(4, (value / max) * 100) : 0;
                const color = market
                  ? agentMarketSliceColor(market, sIndex)
                  : agentMarketSliceColor('us', sIndex);
                return (
                  <div
                    key={s.label}
                    className="agent-viz-bar__col"
                    style={{ height: `${heightPct}%`, background: color }}
                    title={`${s.label}: ${value ?? '—'}`}
                  />
                );
              })}
            </div>
            <span className="agent-viz-bar__label">{cat}</span>
          </div>
        ))}
      </div>
      <div className="agent-viz-bar__legend">
        {series.map((s, index) => (
          <span key={s.label} className="agent-viz-bar__legend-item">
            <i
              style={{
                background: market
                  ? agentMarketSliceColor(market, index)
                  : agentMarketSliceColor('us', index),
              }}
            />
            {s.label}
          </span>
        ))}
      </div>
    </BlockShell>
  );
}

function HbarRankBlock({ block }: { block: AgentVizBlock }) {
  const gainers = (block.payload.gainers as AgentVizRankItem[] | undefined) ?? [];
  const losers = (block.payload.losers as AgentVizRankItem[] | undefined) ?? [];
  const market = normalizeAgentMarket(block.payload.market);
  const maxAbs = Math.max(
    ...[...gainers, ...losers].map((item) => Math.abs(item.value)),
    0.01,
  );
  const renderSide = (items: AgentVizRankItem[], tone: 'up' | 'down') => (
    <div className={`agent-viz-hbar__col agent-viz-hbar__col--${tone}`}>
      {items.map((item) => (
        <div key={item.label} className="agent-viz-hbar__row">
          <span className="agent-viz-hbar__label">{item.label}</span>
          <div className="agent-viz-hbar__track">
            <div
              className={`agent-viz-hbar__fill agent-viz-hbar__fill--${tone}`}
              style={{
                width: `${(Math.abs(item.value) / maxAbs) * 100}%`,
                background: market && tone === 'up' ? agentMarketLineColor(market) : undefined,
              }}
            />
          </div>
          <span className={`agent-viz-hbar__value agent-viz-hbar__value--${tone}`}>
            {formatVizPercent(item.value)}
          </span>
        </div>
      ))}
    </div>
  );
  return (
    <BlockShell block={block}>
      <div className={`agent-viz-hbar${market ? ` agent-viz-hbar--${market}` : ''}`}>
        {gainers.length ? renderSide(gainers, 'up') : null}
        {losers.length ? renderSide(losers, 'down') : null}
      </div>
    </BlockShell>
  );
}

function DonutBlock({ block }: { block: AgentVizBlock }) {
  const slices = (block.payload.slices as AgentVizDonutSlice[] | undefined) ?? [];
  const market = normalizeAgentMarket(block.payload.market);
  if (!slices.length) return null;
  const colored = slices.map((slice, index) => ({
    key: slice.key,
    name: slice.label,
    value: slice.value,
    color: agentMarketSliceColor(market ?? slice.market, index),
    ratio: 0,
  }));
  const total = colored.reduce((sum, slice) => sum + slice.value, 0) || 1;
  const normalized = colored.map((slice) => ({
    ...slice,
    ratio: slice.value / total,
  }));
  const paths = buildDonutPaths(normalized, 50, 50, 46, 28);
  const legendColumns = normalized.length <= 2 ? normalized.length : normalized.length <= 4 ? 2 : 3;

  return (
    <BlockShell block={block}>
      <div className={`agent-viz-donut${market ? ` agent-viz-donut--${market}` : ''}`}>
        <div className="agent-viz-donut__chart-wrap">
          <svg viewBox="0 0 100 100" className="agent-viz-donut__chart" role="img">
            {paths.map((segment) => (
              <path key={segment.key} d={segment.path} fill={segment.color} />
            ))}
          </svg>
        </div>
        <ul
          className="agent-viz-donut__legend"
          style={{ gridTemplateColumns: `repeat(${legendColumns}, max-content)` }}
        >
          {normalized.slice(0, 8).map((slice) => (
            <li key={slice.key}>
              <i style={{ background: slice.color }} aria-hidden />
              <span className="agent-viz-donut__entry">
                <span className="agent-viz-donut__name">{slice.name}</span>
                <em>{formatVizPercent(slice.ratio * 100)}</em>
              </span>
            </li>
          ))}
        </ul>
      </div>
    </BlockShell>
  );
}

function TimelineBlock({ block }: { block: AgentVizBlock }) {
  const items = (block.payload.items as AgentVizTimelineItem[] | undefined) ?? [];
  if (!items.length) return null;
  return (
    <BlockShell block={block}>
      <ul className="agent-viz-timeline">
        {items.map((item, index) => (
          <li key={`${item.date}-${index}`} className="agent-viz-timeline__item">
            <time className="agent-viz-timeline__date">{item.date ?? '—'}</time>
            <div className="agent-viz-timeline__content">
              <strong>{item.title ?? '—'}</strong>
              {item.summary ? <p>{item.summary}</p> : null}
              {item.source ? <span className="agent-viz-timeline__source">{item.source}</span> : null}
            </div>
          </li>
        ))}
      </ul>
    </BlockShell>
  );
}

export function AgentVizBlockView({ block }: { block: AgentVizBlock }) {
  switch (block.kind) {
    case 'kpi_row':
      return <KpiRowBlock block={block} />;
    case 'quote_card':
      return <QuoteCardBlock block={block} />;
    case 'table':
      return <TableBlock block={block} />;
    case 'sparkline':
      return <SparklineBlock block={block} />;
    case 'line':
      return <LineBlock block={block} />;
    case 'price_kline':
      return <PriceKlineBlock block={block} />;
    case 'bar':
      return <BarBlock block={block} />;
    case 'hbar_rank':
      return <HbarRankBlock block={block} />;
    case 'donut':
      return <DonutBlock block={block} />;
    case 'timeline':
      return <TimelineBlock block={block} />;
    default:
      return null;
  }
}

export function AgentVizPanel({ blocks }: { blocks: AgentVizBlock[] }) {
  const { t, locale } = useTranslation();
  if (!blocks.length) return null;
  const localizedBlocks = localizeAgentVizBlocks(blocks, t, locale);
  return (
    <section className="agent-viz-panel" aria-label={t('agentViz.panelAria')}>
      {localizedBlocks.map((block) => (
        <AgentVizBlockView key={block.id} block={block} />
      ))}
    </section>
  );
}
