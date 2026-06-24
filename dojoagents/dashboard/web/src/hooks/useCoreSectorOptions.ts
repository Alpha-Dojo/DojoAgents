import { useCallback, useEffect, useState } from 'react';
import { fetchCoreTickerSector } from '../api/dojoCore';
import { cacheKeys } from '../cache/cacheKeys';
import { fetchCached, getCached, invalidateCache } from '../cache/queryCache';
import type { CoreTickerContext } from '../navigation/coreContext';
import type { CoreSectorOption } from '../types/dojoCore';

interface CoreSectorOptionsCache {
  sectorOptions: CoreSectorOption[];
  loadedKey: string;
}

export function useCoreSectorOptions(ctx: CoreTickerContext | null) {
  const cacheKey = ctx?.ticker ? cacheKeys.coreTickerSector(ctx.market, ctx.ticker) : null;
  const requestKey = ctx?.ticker ? `${ctx.market ?? ''}:${ctx.ticker}` : '';

  const [sectorOptions, setSectorOptions] = useState<CoreSectorOption[]>(() => {
    const cached = cacheKey ? getCached<CoreSectorOptionsCache>(cacheKey) : null;
    return cached?.sectorOptions ?? [];
  });
  const [loading, setLoading] = useState(() => (cacheKey ? !getCached(cacheKey) : false));
  const [error, setError] = useState<string | null>(null);
  const [loadedKey, setLoadedKey] = useState(() => {
    const cached = cacheKey ? getCached<CoreSectorOptionsCache>(cacheKey) : null;
    return cached?.loadedKey ?? '';
  });
  const [reloadTick, setReloadTick] = useState(0);

  const reload = useCallback(() => {
    if (cacheKey) invalidateCache(cacheKey);
    setReloadTick((n) => n + 1);
  }, [cacheKey]);

  useEffect(() => {
    if (!ctx?.ticker || !cacheKey) {
      setSectorOptions([]);
      setLoadedKey('');
      setError(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    const cached = getCached<CoreSectorOptionsCache>(cacheKey);
    if (cached) {
      setSectorOptions(cached.sectorOptions);
      setLoadedKey(cached.loadedKey);
      setLoading(false);
    } else {
      setSectorOptions([]);
      setLoadedKey('');
      setLoading(true);
    }
    setError(null);

    fetchCached(cacheKey, () =>
      fetchCoreTickerSector({ ticker: ctx.ticker, market: ctx.market }).then((response) => ({
        sectorOptions: response.sector_options,
        loadedKey: `${response.market}:${response.ticker}`,
      })),
    )
      .then((entry) => {
        if (cancelled) return;
        setSectorOptions(entry.sectorOptions);
        setLoadedKey(entry.loadedKey);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (!cached) {
          setSectorOptions([]);
          setLoadedKey('');
        }
        setError(err instanceof Error ? err.message : 'Failed to load sector options');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [ctx?.ticker, ctx?.market, cacheKey, reloadTick]);

  const optionsReady = !loading && loadedKey === requestKey && requestKey !== '';

  return { sectorOptions, loading, error, reload, optionsReady, requestKey };
}
