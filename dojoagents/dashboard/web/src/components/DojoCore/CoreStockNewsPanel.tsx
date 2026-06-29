import { useMemo } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import type { CoreStockNewsItem } from '../../types/dojoCore';
import { LoadingIndicator } from '../ui/LoadingIndicator';
import { CoreCard } from './CoreCard';

interface CoreStockNewsPanelProps {
  items: CoreStockNewsItem[];
  loading?: boolean;
}

export function CoreStockNewsPanel({ items, loading = false }: CoreStockNewsPanelProps) {
  const { t } = useTranslation();

  const visibleItems = useMemo(
    () => items.filter((item) => item.date || item.title),
    [items],
  );

  return (
    <CoreCard title={t('core.newsTitle')} className="core-card--news">
      <div className="core-news">
        {loading && !visibleItems.length ? (
          <LoadingIndicator
            className="core-chart-stage__status"
            label={t('core.newsLoading')}
            variant="panel"
          />
        ) : null}
        {!loading && !visibleItems.length ? (
          <p className="core-chart-stage__status">{t('core.newsEmpty')}</p>
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
    </CoreCard>
  );
}
