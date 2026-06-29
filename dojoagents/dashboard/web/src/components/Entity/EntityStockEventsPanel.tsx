import { useMemo } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import type { EntityStockEventItem } from '../../types/entity';
import { EntityCard } from './EntityCard';

interface EntityStockEventsPanelProps {
  events: EntityStockEventItem[];
  loading?: boolean;
}

export function EntityStockEventsPanel({ events, loading = false }: EntityStockEventsPanelProps) {
  const { t } = useTranslation();

  const visibleEvents = useMemo(
    () => events.filter((event) => event.date || event.content),
    [events],
  );

  return (
    <EntityCard title={t('entityPage.eventsTitle')} className="entity-card--events">
      <div className="core-events">
        {loading && !visibleEvents.length ? (
          <p className="entity-chart-stage__status">{t('entityPage.eventsLoading')}</p>
        ) : null}
        {!loading && !visibleEvents.length ? (
          <p className="entity-chart-stage__status">{t('entityPage.eventsEmpty')}</p>
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
    </EntityCard>
  );
}
