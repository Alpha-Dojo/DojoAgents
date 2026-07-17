import { useEffect, useMemo, useRef, useState, memo, type ReactNode } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import type { MarketCode, SectorItem } from '../../types/market';
import { MARKET_CODE } from '../../utils/marketDisplay';
import {
  abbreviateLabel,
  formatPct,
  layoutSingleMarketTreemap,
  treemapHeatFill,
  treemapLabelTier,
  type MarketSectorMove,
  type TreemapRect,
} from '../../utils/marketSectorTreemap';

interface MarketSectorTreemapProps {
  market: MarketCode;
  moves: MarketSectorMove[];
  maxAbs: number;
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
  onSectorJump?: (sector: SectorItem, market: MarketCode) => void;
}

interface TreemapTileProps {
  rect: TreemapRect;
  maxAbs: number;
  label: string;
  onSelect: () => void;
}

function TreemapTile({ rect, maxAbs, label, onSelect }: TreemapTileProps) {
  const { move, x, y, w, h } = rect;
  const up = move.change_percent >= 0;
  const tier = treemapLabelTier(w, h);
  const labelMax = Math.max(4, Math.floor(w / 7));
  const nameSize = Math.min(13, Math.max(9.5, Math.sqrt(w * h) * 0.054));
  const pctSize = Math.min(14.5, Math.max(10.5, nameSize + 1.2));
  const centerY = y + h / 2;
  const nameY = tier === 'full' ? centerY - pctSize * 0.55 : centerY;
  const pctY = tier === 'full' ? centerY + nameSize * 0.75 : centerY;

  return (
    <g className="mesh-sector-treemap__tile" onClick={onSelect} style={{ cursor: 'pointer' }}>
      <rect
        x={x}
        y={y}
        width={w}
        height={h}
        rx={2}
        fill={treemapHeatFill(move.change_percent, maxAbs)}
        stroke="rgb(0 0 0 / 18%)"
        strokeWidth={0.5}
      />
      {tier === 'full' ? (
        <text
          x={x + w / 2}
          y={nameY}
          textAnchor="middle"
          dominantBaseline="middle"
          className="mesh-sector-treemap__label"
          style={{ fontSize: nameSize }}
        >
          {abbreviateLabel(label, labelMax)}
        </text>
      ) : null}
      {tier === 'full' || tier === 'pct' ? (
        <text
          x={x + w / 2}
          y={pctY}
          textAnchor="middle"
          dominantBaseline="middle"
          className={`mesh-sector-treemap__pct${up ? ' mesh-sector-treemap__pct--up' : ' mesh-sector-treemap__pct--down'}`}
          style={{ fontSize: pctSize }}
        >
          {formatPct(move.change_percent)}
        </text>
      ) : null}
      <title>{`${label} ${formatPct(move.change_percent)}`}</title>
    </g>
  );
}

export const MarketSectorTreemap = memo(function MarketSectorTreemap({
  market,
  moves,
  maxAbs,
  loading = false,
  error = null,
  onRetry,
  onSectorJump,
}: MarketSectorTreemapProps) {
  const { t, text } = useTranslation();
  const containerRef = useRef<HTMLElement>(null);
  const [layoutSize, setLayoutSize] = useState({ width: 0, height: 0 });
  const clipId = `mesh-treemap-clip-${market}`;
  const showLoading = loading && moves.length === 0;
  const showError = Boolean(error) && moves.length === 0 && !loading;

  // Keep the measured container mounted for the whole lifecycle so ResizeObserver
  // attaches on first paint (do not early-return a different DOM tree while loading).
  useEffect(() => {
    const element = containerRef.current;
    if (!element) return;

    const updateSize = () => {
      const width = Math.floor(element.clientWidth);
      const height = Math.floor(element.clientHeight);
      if (width > 0 && height > 0) {
        setLayoutSize((current) =>
          current.width === width && current.height === height ? current : { width, height },
        );
      }
    };

    updateSize();
    const frame = requestAnimationFrame(updateSize);
    const observer = new ResizeObserver(updateSize);
    observer.observe(element);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, []);

  const layout = useMemo(() => {
    if (layoutSize.width <= 0 || layoutSize.height <= 0) return null;
    return layoutSingleMarketTreemap(moves, market, layoutSize.width, layoutSize.height);
  }, [layoutSize, market, moves]);

  let body: ReactNode = null;
  if (showLoading) {
    body = <p className="mesh-sector-treemap__status">{t('marketPage.discoveryLoading')}</p>;
  } else if (showError) {
    body = (
      <>
        <p className="mesh-sector-treemap__status">{t('marketPage.discoveryLoadFailed')}</p>
        {onRetry ? (
          <button type="button" className="market-view__retry" onClick={onRetry}>
            {t('marketPage.retry')}
          </button>
        ) : null}
      </>
    );
  } else if (layoutSize.width > 0 && layout && layout.rects.length === 0) {
    body = <p className="mesh-sector-treemap__status">{t('marketPage.discoveryNoData')}</p>;
  } else if (layout && layout.rects.length > 0) {
    body = (
      <svg
        viewBox={`0 0 ${layout.width} ${layout.height}`}
        className="mesh-sector-treemap__canvas"
        width="100%"
        height={layout.height}
        preserveAspectRatio="none"
        role="img"
        aria-label={`${t('marketPage.dailyDiscoveryTitle')} · ${MARKET_CODE[market]}`}
      >
        <defs>
          <clipPath id={clipId}>
            <rect x={0} y={0} width={layout.width} height={layout.height} rx={4} />
          </clipPath>
        </defs>
        <g clipPath={`url(#${clipId})`}>
          {layout.rects.map((rect) => (
            <TreemapTile
              key={`${rect.move.market}:${rect.move.concept_code}`}
              rect={rect}
              maxAbs={maxAbs}
              label={text(rect.move.name)}
              onSelect={() => onSectorJump?.(rect.move, rect.move.market)}
            />
          ))}
        </g>
      </svg>
    );
  }

  return (
    <section
      ref={containerRef}
      className={`mesh-sector-treemap${showLoading || showError || (layout && layout.rects.length === 0) ? ' mesh-sector-treemap--status' : ''}`}
      aria-busy={showLoading || undefined}
      aria-label={`${t('marketPage.dailyDiscoveryTitle')} · ${MARKET_CODE[market]}`}
    >
      {body}
    </section>
  );
});
