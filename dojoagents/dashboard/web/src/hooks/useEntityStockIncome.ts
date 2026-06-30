import { useEffect, useState } from 'react';
import { fetchCoreTickerIncome } from '../api/entity';
import { cacheKeys } from '../cache/cacheKeys';
import { fetchCached, getCached } from '../cache/queryCache';
import type { EntityTickerContext } from '../navigation/entityContext';
import type { EntityTickerIncomeResponse } from '../types/entity';

interface CoreStockIncomeCache {
  data: EntityTickerIncomeResponse;
  loadedKey: string;
}

export function useEntityStockIncome(ctx: EntityTickerContext | null) {
  const cacheKey = ctx?.ticker ? cacheKeys.coreTickerIncome(ctx.market, ctx.ticker) : null;
  const requestKey = ctx?.ticker ? `${ctx.market ?? ''}:${ctx.ticker}` : '';

  const [data, setData] = useState<EntityTickerIncomeResponse | null>(() => {
    const cached = cacheKey ? getCached<CoreStockIncomeCache>(cacheKey) : null;
    return cached?.data ?? null;
  });
  const [loading, setLoading] = useState(() => (cacheKey ? !getCached(cacheKey) : false));
  const [error, setError] = useState<string | null>(null);
  const [loadedKey, setLoadedKey] = useState(() => {
    const cached = cacheKey ? getCached<CoreStockIncomeCache>(cacheKey) : null;
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
    const cached = getCached<CoreStockIncomeCache>(cacheKey);
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
      fetchCoreTickerIncome({
        ticker: ctx.ticker,
        market: ctx.market,
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
        setError(err instanceof Error ? err.message : 'Failed to load income distribution');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [ctx?.ticker, ctx?.market, cacheKey]);

  const ready = !loading && loadedKey === requestKey && requestKey !== '';

  return { data, loading, error, ready, requestKey };
}
