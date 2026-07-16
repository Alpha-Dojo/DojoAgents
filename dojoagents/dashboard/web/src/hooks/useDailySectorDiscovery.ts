import { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchDailySectorDiscovery } from '../api/market';
import { cacheKeys } from '../cache/cacheKeys';
import { fetchCached, getCached, invalidateCache } from '../cache/queryCache';
import type { MarketCode, SectorItem } from '../types/market';
import {
  TREEMAP_TOP_N,
  mergeMarketMovers,
  type MarketSectorMove,
} from '../utils/marketSectorTreemap';
import {
  minCapKeyFromFilters,
  minCapThresholdsFromYi,
  type MeshSectorFilterState,
} from '../utils/marketSectorFilters';
import { useMarketDataCacheEpoch } from './useMarketDataCacheEpoch';

type DiscoveryPayload = Partial<
  Record<MarketCode, { gainers: SectorItem[]; losers: SectorItem[] }>
>;

interface UseDailySectorDiscoveryResult {
  moves: MarketSectorMove[];
  loading: boolean;
  error: string | null;
  reload: () => void;
}

export function useDailySectorDiscovery(
  filters: Pick<MeshSectorFilterState, 'minCapYi'> & { asOfDate?: string },
): UseDailySectorDiscoveryResult {
  const cacheEpoch = useMarketDataCacheEpoch();
  const asOfDate = (filters.asOfDate || '').trim();
  const capKey = useMemo(
    () =>
      minCapKeyFromFilters({
        minCapYi: filters.minCapYi,
        days: 1,
        sectorLimit: TREEMAP_TOP_N,
      }),
    [filters.minCapYi],
  );
  const cacheKey = cacheKeys.marketDailyDiscovery(TREEMAP_TOP_N, capKey, asOfDate);

  const [payload, setPayload] = useState<DiscoveryPayload | null>(() =>
    getCached<DiscoveryPayload>(cacheKey),
  );
  const [loading, setLoading] = useState(() => !getCached<DiscoveryPayload>(cacheKey));
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  const reload = useCallback(() => {
    invalidateCache(cacheKey);
    setTick((n) => n + 1);
  }, [cacheKey]);

  useEffect(() => {
    let cancelled = false;
    if (!asOfDate) {
      setPayload(null);
      setLoading(false);
      setError(null);
      return () => {
        cancelled = true;
      };
    }

    const cached = getCached<DiscoveryPayload>(cacheKey);
    if (cached) {
      setPayload(cached);
      setLoading(false);
    } else {
      setLoading(true);
    }
    setError(null);

    const min_cap_by_market = minCapThresholdsFromYi(filters.minCapYi);

    fetchCached(cacheKey, () =>
      fetchDailySectorDiscovery({
        sectorLimit: TREEMAP_TOP_N,
        asOfDate,
        minCapByMarket: min_cap_by_market,
      }),
    )
      .then((next) => {
        if (!cancelled) setPayload(next);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          if (!cached) setPayload(null);
          setError(err instanceof Error ? err.message : 'Failed to load daily discovery');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [cacheKey, filters.minCapYi, asOfDate, tick, cacheEpoch]);

  const moves = useMemo(() => mergeMarketMovers(payload ?? {}), [payload]);

  return {
    moves,
    loading,
    error,
    reload,
  };
}
