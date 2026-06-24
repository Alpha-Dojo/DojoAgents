import { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchDojoMeshOverview } from '../api/dojoMesh';
import { cacheKeys } from '../cache/cacheKeys';
import { fetchCached, getCached, invalidateCache } from '../cache/queryCache';
import type { DojoMeshOverview } from '../types/dojoMesh';
import type { MeshSectorFilterState } from '../utils/meshSectorFilters';
import { minCapKeyFromFilters, minCapThresholdsFromYi } from '../utils/meshSectorFilters';

interface UseDojoMeshOverviewResult {
  data: DojoMeshOverview | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
}

export function useDojoMeshOverview(filters: MeshSectorFilterState): UseDojoMeshOverviewResult {
  const capKey = useMemo(() => minCapKeyFromFilters(filters), [filters]);
  const cacheKey = cacheKeys.dojoMeshOverview(filters.sectorLimit, filters.days, capKey);

  const [data, setData] = useState<DojoMeshOverview | null>(() => getCached<DojoMeshOverview>(cacheKey));
  const [loading, setLoading] = useState(() => !getCached<DojoMeshOverview>(cacheKey));
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  const reload = useCallback(() => {
    invalidateCache(cacheKey);
    setTick((n) => n + 1);
  }, [cacheKey]);

  useEffect(() => {
    let cancelled = false;
    const cached = getCached<DojoMeshOverview>(cacheKey);
    if (cached) {
      setData(cached);
      setLoading(false);
    } else {
      setLoading(true);
    }
    setError(null);

    const min_cap_by_market = minCapThresholdsFromYi(filters.minCapYi);

    fetchCached(cacheKey, () =>
      fetchDojoMeshOverview({
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
