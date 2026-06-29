import { useMemo } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import type { CoreStockEventItem } from '../../types/dojoCore';
import { LoadingIndicator } from '../ui/LoadingIndicator';
import { CoreCard } from './CoreCard';

interface CoreStockEventsPanelProps {
  events: CoreStockEventItem[];
  loading?: boolean;
}

export function CoreStockEventsPanel({ events, loading = false }: CoreStockEventsPanelProps) {
  const { t } = useTranslation();

  const visibleEvents = useMemo(
    () => events.filter((event) => event.date || event.content),
    [events],
  );

  return (
    <CoreCard title={t('core.eventsTitle')} className="core-card--events">
      <div className="core-events">
        {loading && !visibleEvents.length ? (
          <LoadingIndicator
            className="core-chart-stage__status"
            label={t('core.eventsLoading')}
            variant="panel"
          />
        ) : null}
        {!loading && !visibleEvents.length ? (
          <p className="core-chart-stage__status">{t('core.eventsEmpty')}</p>
        ) : null}

        {visibleEvents.length ? (
          <ul className="core-events__list">
            {visibleEvents.map((event) => (
              <li key={event.id} className="core-events__item" title={event.content || undefined}>
                {event.date ? (
                  <time className="core-events__date" dateTime={event.date}>
                    {event.date}
                  </time>
                ) : null}
                {event.typeLabel ? (
                  <span className="core-events__type">{event.typeLabel}</span>
                ) : null}
                <span className="core-events__content">{event.content || '—'}</span>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </CoreCard>
  );
}
