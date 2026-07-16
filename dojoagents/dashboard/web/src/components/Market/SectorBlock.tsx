import { useLayoutEffect, useRef } from 'react';
import type { MarketCode, SectorItem, SectorMemberItem } from '../../types/market';
import { useTranslation } from '../../hooks/useTranslation';
import type { OrderedSectorRow } from '../../utils/sectorLink';
import { sectorLinkKey } from '../../utils/sectorLink';
import { scrollElementIntoScrollContainer } from '../../utils/scrollIntoContainer';
import { SectorRow } from './SectorRow';

interface SectorBlockProps {
  market: MarketCode;
  variant: 'gain' | 'loss';
  lookbackDays?: number;
  title: string;
  subtitle?: string;
  rows: OrderedSectorRow[];
  loading?: boolean;
  scrollToLinkKey?: string | null;
  onSectorSelect?: (sector: SectorItem) => void;
  onSectorJump?: (sector: SectorItem) => void;
  onTickerClick?: (member: SectorMemberItem, sector: SectorItem) => void;
}

export function SectorBlock({
  market,
  variant,
  lookbackDays = 1,
  title,
  subtitle,
  rows,
  loading = false,
  scrollToLinkKey,
  onSectorSelect,
  onSectorJump,
  onTickerClick,
}: SectorBlockProps) {
  const { t } = useTranslation();
  const listRef = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    if (!scrollToLinkKey) return;
    const list = listRef.current;
    if (!list) return;

    let cancelled = false;
    const scrollToTarget = (retriesLeft: number) => {
      if (cancelled) return;
      const target = list.querySelector<HTMLElement>(`[data-scroll-target="${scrollToLinkKey}"]`);
      if (target) {
        scrollElementIntoScrollContainer(list, target);
        return;
      }
      if (retriesLeft > 0) {
        window.setTimeout(() => scrollToTarget(retriesLeft - 1), 40);
      }
    };

    requestAnimationFrame(() => scrollToTarget(8));
    return () => {
      cancelled = true;
    };
  }, [scrollToLinkKey, rows]);

  return (
    <section className={`mesh-sector-block mesh-sector-block--${variant}`} aria-label={title}>
      <header className={`mesh-sector-block__head mesh-sector-block__head--${variant}`}>
        <div className="mesh-sector-block__titles">
          <h3 className="mesh-sector-block__title">{title}</h3>
          {subtitle ? <span className="mesh-sector-block__sub">{subtitle}</span> : null}
        </div>
        <span className="mesh-sector-block__count">{rows.length}</span>
      </header>
      <div className="mesh-sector-block__list" ref={listRef}>
        {rows.map((row) => {
          const rowLinkKey = sectorLinkKey(row.sector.concept_code);
          const isScrollTarget =
            Boolean(scrollToLinkKey) &&
            Boolean(row.scrollIntoView) &&
            rowLinkKey === scrollToLinkKey;
          return (
            <div
              key={`${row.sector.concept_code}${row.injected ? '-injected' : ''}${row.missing ? '-missing' : ''}`}
              className="mesh-sector-block__row-wrap"
              {...(isScrollTarget && rowLinkKey ? { 'data-scroll-target': rowLinkKey } : {})}
            >
              <SectorRow
                market={market}
                sector={row.sector}
                variant={variant}
                lookbackDays={lookbackDays}
                selected={row.selected}
                missing={row.missing}
                onSelect={row.missing ? undefined : () => onSectorSelect?.(row.sector)}
                onJump={row.missing ? undefined : () => onSectorJump?.(row.sector)}
                onTickerClick={row.missing ? undefined : onTickerClick}
              />
            </div>
          );
        })}
        {rows.length === 0 ? (
          <p className="mesh-sector-block__empty">
            {loading
              ? t('marketPage.loading')
              : variant === 'gain'
                ? t('sector.emptyGainers')
                : t('sector.emptyLosers')}
          </p>
        ) : null}
      </div>
    </section>
  );
}
