import { useTranslation } from '../../hooks/useTranslation';
import type { CoreSectorOption } from '../../types/dojoCore';
import { formatSectorOptionL3 } from '../../utils/coreSectorOptions';

interface CoreSectorCycleButtonProps {
  options: CoreSectorOption[];
  activeIndex: number;
  classificationRole: 'primary' | 'secondary';
  loading: boolean;
  onCycle: () => void;
}

export function CoreSectorCycleButton({
  options,
  activeIndex,
  classificationRole,
  loading,
  onCycle,
}: CoreSectorCycleButtonProps) {
  const { t, text } = useTranslation();

  const canCycle = !loading && options.length >= 2;
  const nextIndex = options.length >= 2 ? (activeIndex + 1) % options.length : 0;
  const nextL3 = options.length >= 2 ? formatSectorOptionL3(options[nextIndex], text) : '';

  const title = loading
    ? t('core.cycleSectorLoading')
    : canCycle
      ? t('core.cycleSectorTo', { name: nextL3 })
      : t('core.cycleSectorRetry');

  return (
    <button
      type="button"
      className={`core-sector-cycle core-sector-cycle--${classificationRole}${loading ? ' core-sector-cycle--loading' : ''}`}
      aria-label={t('core.cycleSector')}
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
