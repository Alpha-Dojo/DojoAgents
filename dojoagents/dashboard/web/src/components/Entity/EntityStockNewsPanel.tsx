import { useMemo } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import type { EntityStockNewsItem } from '../../types/entity';
import { EntityCard } from './EntityCard';

interface EntityStockNewsPanelProps {
  items: EntityStockNewsItem[];
  loading?: boolean;
}

export function EntityStockNewsPanel({ items, loading = false }: EntityStockNewsPanelProps) {
  const { t } = useTranslation();

  const visibleItems = useMemo(
    () => items.filter((item) => item.date || item.title),
    [items],
  );

  return (
    <EntityCard title={t('entityPage.newsTitle')} className="entity-card--news">
      <div className="core-news">
        {loading && !visibleItems.length ? (
          <p className="entity-chart-stage__status">{t('entityPage.newsLoading')}</p>
        ) : null}
        {!loading && !visibleItems.length ? (
          <p className="entity-chart-stage__status">{t('entityPage.newsEmpty')}</p>
        ) : null}

        {visibleItems.length ? (
          <ul className="core-news__list">
            {visibleItems.map((item) => (
              <li key={item.id} className="core-news__item">
                {item.date ? (
                  <time className="core-news__date" dateTime={item.date}>
                    {item.date}
                  </time>
                ) : null}
                {item.url ? (
                  <a
                    href={item.url}
                    className="core-news__link"
                    target="_blank"
                    rel="noopener noreferrer"
                    title={item.title}
                  >
                    {item.title}
                  </a>
                ) : (
                  <span className="core-news__title">{item.title}</span>
                )}
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </EntityCard>
  );
}
