import { useEffect, useState } from 'react';
import { fetchCoreTickerNews } from '../api/dojoCore';
import { cacheKeys } from '../cache/cacheKeys';
import { fetchCached, getCached } from '../cache/queryCache';
import type { CoreTickerContext } from '../navigation/coreContext';
import type { CoreTickerNewsResponse } from '../types/dojoCore';

const DEFAULT_PAGE_SIZE = 20;

interface CoreStockNewsCache {
  data: CoreTickerNewsResponse;
  loadedKey: string;
}

export function useCoreStockNews(ctx: CoreTickerContext | null, pageSize = DEFAULT_PAGE_SIZE) {
  const cacheKey =
    ctx?.ticker ? cacheKeys.coreTickerNews(ctx.market, ctx.ticker, pageSize) : null;
  const requestKey = ctx?.ticker ? `${ctx.market ?? ''}:${ctx.ticker}` : '';

  const [data, setData] = useState<CoreTickerNewsResponse | null>(() => {
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
  }, [ctx?.ticker, ctx?.market, pageSize, cacheKey]);

  const ready = !loading && loadedKey === requestKey && requestKey !== '';

  return { data, loading, error, ready, requestKey };
}
