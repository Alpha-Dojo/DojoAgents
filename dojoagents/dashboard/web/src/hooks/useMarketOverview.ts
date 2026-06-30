import { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchMarketOverview } from '../api/market';
import { cacheKeys } from '../cache/cacheKeys';
import { fetchCached, getCached, invalidateCache } from '../cache/queryCache';
import type { MarketOverview } from '../types/market';
import type { MeshSectorFilterState } from '../utils/marketSectorFilters';
import { minCapKeyFromFilters, minCapThresholdsFromYi } from '../utils/marketSectorFilters';

interface UseMarketOverviewResult {
  data: MarketOverview | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
}

export function useMarketOverview(filters: MeshSectorFilterState): UseMarketOverviewResult {
  const capKey = useMemo(() => minCapKeyFromFilters(filters), [filters]);
  const cacheKey = cacheKeys.marketOverview(filters.sectorLimit, filters.days, capKey);

  const [data, setData] = useState<MarketOverview | null>(() => getCached<MarketOverview>(cacheKey));
  const [loading, setLoading] = useState(() => !getCached<MarketOverview>(cacheKey));
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  const reload = useCallback(() => {
    invalidateCache(cacheKey);
    setTick((n) => n + 1);
  }, [cacheKey]);

  useEffect(() => {
    let cancelled = false;
    const cached = getCached<MarketOverview>(cacheKey);
    if (cached) {
      setData(cached);
      setLoading(false);
    } else {
      setLoading(true);
    }
    setError(null);

    const min_cap_by_market = minCapThresholdsFromYi(filters.minCapYi);

    fetchCached(cacheKey, () =>
      fetchMarketOverview({
        sector_limit: filters.sectorLimit,
        days: filters.days,
        min_cap_by_market,
      }),
    )
      .then((overview) => {
        if (!cancelled) setData(overview);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          if (!cached) setData(null);
          setError(err instanceof Error ? err.message : '加载 DojoMesh 数据失败');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [cacheKey, filters.days, filters.sectorLimit, capKey, tick]);

  return { data, loading, error, reload };
}
