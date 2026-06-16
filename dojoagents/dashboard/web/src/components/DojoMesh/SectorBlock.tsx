import type { SectorItem, SectorMemberItem } from '../../types/dojoMesh';
import { useTranslation } from '../../hooks/useTranslation';
import type { OrderedSectorRow } from '../../utils/sectorLink';
import { SectorRow } from './SectorRow';

interface SectorBlockProps {
  variant: 'gain' | 'loss';
  title: string;
  subtitle?: string;
  rows: OrderedSectorRow[];
  onSectorSelect?: (sector: SectorItem) => void;
  onSectorJump?: (sector: SectorItem) => void;
  onTickerClick?: (member: SectorMemberItem, sector: SectorItem) => void;
}

export function SectorBlock({
  variant,
  title,
  subtitle,
  rows,
  onSectorSelect,
  onSectorJump,
  onTickerClick,
}: SectorBlockProps) {
  const { t } = useTranslation();

  return (
    <section className={`mesh-sector-block mesh-sector-block--${variant}`} aria-label={title}>
      <header className={`mesh-sector-block__head mesh-sector-block__head--${variant}`}>
        <div className="mesh-sector-block__titles">
          <h3 className="mesh-sector-block__title">{title}</h3>
          {subtitle ? <span className="mesh-sector-block__sub">{subtitle}</span> : null}
        </div>
        <span className="mesh-sector-block__count">{rows.length}</span>
      </header>
      <div className="mesh-sector-block__list">
        {rows.map((row, index) => (
          <div
            key={`${row.sector.concept_code}${row.missing ? '-missing' : ''}`}
            className="mesh-sector-block__row-wrap"
          >
            <SectorRow
              sector={row.sector}
              variant={variant}
              selected={row.selected}
              linked={row.linked}
              missing={row.missing}
              onSelect={row.missing ? undefined : () => onSectorSelect?.(row.sector)}
              onJump={row.missing ? undefined : () => onSectorJump?.(row.sector)}
              onTickerClick={row.missing ? undefined : onTickerClick}
            />
            {row.linked && index === 0 && rows.length > 1 ? (
              <div className="mesh-sector-block__link-gap" aria-hidden />
            ) : null}
          </div>
        ))}
        {rows.length === 0 ? (
          <p className="mesh-sector-block__empty">
            {variant === 'gain' ? t('sector.emptyGainers') : t('sector.emptyLosers')}
          </p>
        ) : null}
      </div>
    </section>
  );
}
