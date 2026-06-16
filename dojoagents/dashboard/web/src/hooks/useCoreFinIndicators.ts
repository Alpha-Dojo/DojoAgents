import { useEffect, useState } from 'react';
import { fetchCoreTickerFinIndicators } from '../api/dojoCore';
import { cacheKeys } from '../cache/cacheKeys';
import { fetchCached, getCached } from '../cache/queryCache';
import type { CoreTickerContext } from '../navigation/coreContext';
import type { CoreTickerFinIndicatorsResponse } from '../types/dojoCore';

const DEFAULT_LIMIT = 20;

interface CoreFinIndicatorsCache {
  data: CoreTickerFinIndicatorsResponse;
  loadedKey: string;
}

export function useCoreFinIndicators(ctx: CoreTickerContext | null, limit = DEFAULT_LIMIT) {
  const cacheKey =
    ctx?.ticker ? cacheKeys.coreTickerFinIndicators(ctx.market, ctx.ticker, limit) : null;
  const requestKey = ctx?.ticker ? `${ctx.market ?? ''}:${ctx.ticker}` : '';

  const [data, setData] = useState<CoreTickerFinIndicatorsResponse | null>(() => {
    const cached = cacheKey ? getCached<CoreFinIndicatorsCache>(cacheKey) : null;
    return cached?.data ?? null;
  });
  const [loading, setLoading] = useState(() => (cacheKey ? !getCached(cacheKey) : false));
  const [error, setError] = useState<string | null>(null);
  const [loadedKey, setLoadedKey] = useState(() => {
    const cached = cacheKey ? getCached<CoreFinIndicatorsCache>(cacheKey) : null;
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
    const cached = getCached<CoreFinIndicatorsCache>(cacheKey);
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
      fetchCoreTickerFinIndicators({
        ticker: ctx.ticker,
        market: ctx.market,
        limit,
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
        setError(err instanceof Error ? err.message : 'Failed to load financial indicators');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [ctx?.ticker, ctx?.market, limit, cacheKey]);

  const ready = !loading && loadedKey === requestKey && requestKey !== '';

  return { data, loading, error, ready, requestKey };
}
