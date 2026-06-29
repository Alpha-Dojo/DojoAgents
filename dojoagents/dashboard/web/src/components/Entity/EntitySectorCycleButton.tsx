import { useTranslation } from '../../hooks/useTranslation';
import type { EntitySectorOption } from '../../types/entity';
import { formatSectorOptionL3 } from '../../utils/entitySectorOptions';

interface EntitySectorCycleButtonProps {
  options: EntitySectorOption[];
  activeIndex: number;
  classificationRole: 'primary' | 'secondary';
  loading: boolean;
  onCycle: () => void;
}

export function EntitySectorCycleButton({
  options,
  activeIndex,
  classificationRole,
  loading,
  onCycle,
}: EntitySectorCycleButtonProps) {
  const { t, text } = useTranslation();

  const canCycle = !loading && options.length >= 2;
  const nextIndex = options.length >= 2 ? (activeIndex + 1) % options.length : 0;
  const nextL3 = options.length >= 2 ? formatSectorOptionL3(options[nextIndex], text) : '';

  const title = loading
    ? t('entityPage.cycleSectorLoading')
    : canCycle
      ? t('entityPage.cycleSectorTo', { name: nextL3 })
      : t('entityPage.cycleSectorRetry');

  return (
    <button
      type="button"
      className={`core-sector-cycle core-sector-cycle--${classificationRole}${loading ? ' core-sector-cycle--loading' : ''}`}
      aria-label={t('entityPage.cycleSector')}
      aria-busy={loading}
      title={title}
      onClick={onCycle}
    >
      <span className="core-sector-cycle__icon" aria-hidden>
        ⇄
      </span>
    </button>
  );
}
