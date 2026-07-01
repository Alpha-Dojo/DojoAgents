import { useEffect, useState } from 'react';
import { fetchCoreTickerNews } from '../api/entity';
import { cacheKeys } from '../cache/cacheKeys';
import { fetchCached, getCached } from '../cache/queryCache';
import type { EntityTickerContext } from '../navigation/entityContext';
import type { EntityTickerNewsResponse } from '../types/entity';
import { useMarketDataCacheEpoch } from './useMarketDataCacheEpoch';

const DEFAULT_PAGE_SIZE = 20;

interface CoreStockNewsCache {
  data: EntityTickerNewsResponse;
  loadedKey: string;
}

export function useEntityStockNews(ctx: EntityTickerContext | null, pageSize = DEFAULT_PAGE_SIZE) {
  const cacheEpoch = useMarketDataCacheEpoch();
  const cacheKey =
    ctx?.ticker ? cacheKeys.coreTickerNews(ctx.market, ctx.ticker, pageSize) : null;
  const requestKey = ctx?.ticker ? `${ctx.market ?? ''}:${ctx.ticker}` : '';

  const [data, setData] = useState<EntityTickerNewsResponse | null>(() => {
    const cached = cacheKey ? getCached<CoreStockNewsCache>(cacheKey) : null;
    return cached?.data ?? null;
  });
  const [loading, setLoading] = useState(() => (cacheKey ? !getCached(cacheKey) : false));
  const [error, setError] = useState<string | null>(null);
  const [loadedKey, setLoadedKey] = useState(() => {
    const cached = cacheKey ? getCached<CoreStockNewsCache>(cacheKey) : null;
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
    const cached = getCached<CoreStockNewsCache>(cacheKey);
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
      fetchCoreTickerNews({
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
        setError(err instanceof Error ? err.message : 'Failed to load stock news');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [ctx?.ticker, ctx?.market, pageSize, cacheKey, cacheEpoch]);

  const ready = !loading && loadedKey === requestKey && requestKey !== '';

  return { data, loading, error, ready, requestKey };
}
