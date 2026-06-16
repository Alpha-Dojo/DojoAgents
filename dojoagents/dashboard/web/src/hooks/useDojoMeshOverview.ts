import { useCallback, useEffect, useState } from 'react';
import { fetchDojoMeshOverview } from '../api/dojoMesh';
import { cacheKeys } from '../cache/cacheKeys';
import { fetchCached, getCached, invalidateCache } from '../cache/queryCache';
import type { DojoMeshOverview } from '../types/dojoMesh';

interface UseDojoMeshOverviewResult {
  data: DojoMeshOverview | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
}

export function useDojoMeshOverview(sectorLimit = 5): UseDojoMeshOverviewResult {
  const cacheKey = cacheKeys.dojoMeshOverview(sectorLimit);
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

    fetchCached(cacheKey, () => fetchDojoMeshOverview({ sector_limit: sectorLimit }))
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
  }, [cacheKey, sectorLimit, tick]);

  return { data, loading, error, reload };
}
