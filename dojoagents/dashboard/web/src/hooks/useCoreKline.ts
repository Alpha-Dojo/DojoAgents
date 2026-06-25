import { useEffect, useState } from 'react';
import { fetchCoreTickerKline } from '../api/dojoCore';
import { cacheKeys } from '../cache/cacheKeys';
import { fetchCached, getCached } from '../cache/queryCache';
import type { CoreTickerContext } from '../navigation/coreContext';
import type { CoreKlineBar, CoreKlineInterval } from '../types/dojoCore';
import {
  KLINE_INTERVAL_API,
  mapKlineBarsToCore,
  resolveCoreDailyChartWindow,
} from '../utils/coreKline';

interface CoreKlineCache {
  bars: CoreKlineBar[];
  asOf: string | null;
  loadedKey: string;
}

function buildCacheEntry(
  response: Awaited<ReturnType<typeof fetchCoreTickerKline>>,
  interval: CoreKlineInterval,
  market: string | undefined,
): CoreKlineCache {
  return {
    bars: mapKlineBarsToCore(response.bars, interval),
    asOf: response.as_of,
    loadedKey: `${market ?? ''}:${response.symbol}:${interval}`,
  };
}

export function useCoreKline(ctx: CoreTickerContext | null, interval: CoreKlineInterval) {
  const cacheKey =
    ctx?.ticker ? cacheKeys.coreTickerKline(ctx.market, ctx.ticker, interval) : null;
  const requestKey = ctx?.ticker ? `${ctx.market ?? ''}:${ctx.ticker}:${interval}` : '';

  const [bars, setBars] = useState<CoreKlineBar[]>(() => {
    const cached = cacheKey ? getCached<CoreKlineCache>(cacheKey) : null;
    return cached?.bars ?? [];
  });
  const [asOf, setAsOf] = useState<string | null>(() => {
    const cached = cacheKey ? getCached<CoreKlineCache>(cacheKey) : null;
    return cached?.asOf ?? null;
  });
  const [loading, setLoading] = useState(() => (cacheKey ? !getCached(cacheKey) : false));
  const [error, setError] = useState<string | null>(null);
  const [loadedKey, setLoadedKey] = useState(() => {
    const cached = cacheKey ? getCached<CoreKlineCache>(cacheKey) : null;
    return cached?.loadedKey ?? '';
  });

  useEffect(() => {
    if (!ctx?.ticker || !cacheKey) {
      setBars([]);
      setAsOf(null);
      setLoadedKey('');
      setError(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    const cached = getCached<CoreKlineCache>(cacheKey);
    if (cached) {
      setBars(cached.bars);
      setAsOf(cached.asOf);
      setLoadedKey(cached.loadedKey);
      setLoading(false);
    } else {
      setBars([]);
      setAsOf(null);
      setLoadedKey('');
      setLoading(true);
    }
    setError(null);

    const chartWindow = ctx.market ? resolveCoreDailyChartWindow(ctx.market) : null;

    fetchCached(cacheKey, () =>
      fetchCoreTickerKline({
        ticker: ctx.ticker,
        market: ctx.market,
        kline_t: KLINE_INTERVAL_API[interval],
        start_date: chartWindow?.start,
        end_date: chartWindow?.end,
      }).then((response) => buildCacheEntry(response, interval, ctx.market)),
    )
      .then((entry) => {
        if (cancelled) return;
        setBars(entry.bars);
        setAsOf(entry.asOf);
        setLoadedKey(entry.loadedKey);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (!cached) {
          setBars([]);
          setAsOf(null);
          setLoadedKey('');
        }
        setError(err instanceof Error ? err.message : 'Failed to load kline');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [ctx?.ticker, ctx?.market, interval, cacheKey]);

  const ready = !loading && loadedKey === requestKey && requestKey !== '';

  return { bars, asOf, loading, error, ready, requestKey };
}
