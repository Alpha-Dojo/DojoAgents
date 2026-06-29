import { useEffect, useState } from 'react';
import { fetchCoreTickerEvents } from '../api/entity';
import { cacheKeys } from '../cache/cacheKeys';
import { fetchCached, getCached } from '../cache/queryCache';
import type { EntityTickerContext } from '../navigation/entityContext';
import type { EntityTickerEventsResponse } from '../types/entity';

const DEFAULT_PAGE_SIZE = 20;

interface CoreStockEventsCache {
  data: EntityTickerEventsResponse;
  loadedKey: string;
}

export function useEntityStockEvents(ctx: EntityTickerContext | null, pageSize = DEFAULT_PAGE_SIZE) {
  const cacheKey =
    ctx?.ticker ? cacheKeys.coreTickerEvents(ctx.market, ctx.ticker, pageSize) : null;
  const requestKey = ctx?.ticker ? `${ctx.market ?? ''}:${ctx.ticker}` : '';

  const [data, setData] = useState<EntityTickerEventsResponse | null>(() => {
    const cached = cacheKey ? getCached<CoreStockEventsCache>(cacheKey) : null;
    return cached?.data ?? null;
  });
  const [loading, setLoading] = useState(() => (cacheKey ? !getCached(cacheKey) : false));
  const [error, setError] = useState<string | null>(null);
  const [loadedKey, setLoadedKey] = useState(() => {
    const cached = cacheKey ? getCached<CoreStockEventsCache>(cacheKey) : null;
    return cached?.loadedKey ?? '';
  });

  useEffect(() => {
    if (!ctx?.ticker || !cacheKey) {
      setData(null);
      setLoadedKey('');
      setError(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    const cached = getCached<CoreStockEventsCache>(cacheKey);
    if (cached) {
      setData(cached.data);
      setLoadedKey(cached.loadedKey);
      setLoading(false);
    } else {
      setData(null);
      setLoadedKey('');
      setLoading(true);
    }
    setError(null);

    fetchCached(cacheKey, () =>
      fetchCoreTickerEvents({
        ticker: ctx.ticker,
        market: ctx.market,
        page_size: pageSize,
      }).then((response) => ({
        data: response,
        loadedKey: `${response.market}:${response.ticker}`,
      })),
    )
      .then((entry) => {
        if (cancelled) return;
        setData(entry.data);
        setLoadedKey(entry.loadedKey);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (!cached) {
          setData(null);
          setLoadedKey('');
        }
        setError(err instanceof Error ? err.message : 'Failed to load stock events');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [ctx?.ticker, ctx?.market, pageSize, cacheKey]);

  const ready = !loading && loadedKey === requestKey && requestKey !== '';

  return { data, loading, error, ready, requestKey };
}
