import { useCallback, useEffect, useState } from 'react';
import { fetchCoreTickerSector } from '../api/entity';
import { cacheKeys } from '../cache/cacheKeys';
import { fetchCached, getCached, invalidateCache } from '../cache/queryCache';
import type { EntityTickerContext } from '../navigation/entityContext';
import type { EntitySectorOption } from '../types/entity';

interface EntitySectorOptionsCache {
  sectorOptions: EntitySectorOption[];
  loadedKey: string;
}

export function useEntitySectorOptions(ctx: EntityTickerContext | null) {
  const cacheKey = ctx?.ticker ? cacheKeys.coreTickerSector(ctx.market, ctx.ticker) : null;
  const requestKey = ctx?.ticker ? `${ctx.market ?? ''}:${ctx.ticker}` : '';

  const [sectorOptions, setSectorOptions] = useState<EntitySectorOption[]>(() => {
    const cached = cacheKey ? getCached<EntitySectorOptionsCache>(cacheKey) : null;
    return cached?.sectorOptions ?? [];
  });
  const [loading, setLoading] = useState(() => (cacheKey ? !getCached(cacheKey) : false));
  const [error, setError] = useState<string | null>(null);
  const [loadedKey, setLoadedKey] = useState(() => {
    const cached = cacheKey ? getCached<EntitySectorOptionsCache>(cacheKey) : null;
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
    const cached = getCached<EntitySectorOptionsCache>(cacheKey);
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
