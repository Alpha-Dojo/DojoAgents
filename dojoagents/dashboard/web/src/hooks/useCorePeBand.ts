import { useEffect, useState } from 'react';
import { fetchCoreTickerPeBand } from '../api/dojoCore';
import { cacheKeys } from '../cache/cacheKeys';
import { fetchCached, getCached } from '../cache/queryCache';
import type { CoreTickerContext } from '../navigation/coreContext';
import type { CorePeBandPoint } from '../types/dojoCore';
import { resolveCoreDailyChartWindow } from '../utils/coreKline';

interface CorePeBandCache {
  points: CorePeBandPoint[];
  loadedKey: string;
}

export function useCorePeBand(ctx: CoreTickerContext | null) {
  const cacheKey = ctx?.ticker ? cacheKeys.coreTickerPeBand(ctx.market, ctx.ticker) : null;
  const requestKey = ctx?.ticker ? `${ctx.market ?? ''}:${ctx.ticker}` : '';

  const [points, setPoints] = useState<CorePeBandPoint[]>(() => {
    const cached = cacheKey ? getCached<CorePeBandCache>(cacheKey) : null;
    return cached?.points ?? [];
  });
  const [loading, setLoading] = useState(() => (cacheKey ? !getCached(cacheKey) : false));
  const [error, setError] = useState<string | null>(null);
  const [loadedKey, setLoadedKey] = useState(() => {
    const cached = cacheKey ? getCached<CorePeBandCache>(cacheKey) : null;
    return cached?.loadedKey ?? '';
  });

  useEffect(() => {
    if (!ctx?.ticker || !cacheKey) {
      setPoints([]);
      setLoadedKey('');
      setError(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    const cached = getCached<CorePeBandCache>(cacheKey);
    if (cached) {
      setPoints(cached.points);
      setLoadedKey(cached.loadedKey);
      setLoading(false);
    } else {
      setPoints([]);
      setLoadedKey('');
      setLoading(true);
    }
    setError(null);

    const chartWindow = ctx.market ? resolveCoreDailyChartWindow(ctx.market) : null;

    fetchCached(cacheKey, () =>
      fetchCoreTickerPeBand({
        ticker: ctx.ticker,
        market: ctx.market,
        start_date: chartWindow?.start,
        end_date: chartWindow?.end,
      }).then((response) => ({
        points: response.points,
        loadedKey: `${ctx.market ?? ''}:${response.ticker}`,
      })),
    )
      .then((entry) => {
        if (cancelled) return;
        setPoints(entry.points);
        setLoadedKey(entry.loadedKey);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (!cached) {
          setPoints([]);
          setLoadedKey('');
        }
        setError(err instanceof Error ? err.message : 'Failed to load PE band');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [ctx?.ticker, ctx?.market, cacheKey]);

  const ready = !loading && loadedKey === requestKey && requestKey !== '';

  return { points, loading, error, ready, requestKey };
}
