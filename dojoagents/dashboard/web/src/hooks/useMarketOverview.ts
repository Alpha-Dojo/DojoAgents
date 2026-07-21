import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  fetchMarketMeshMovers,
  fetchMarketOverview,
  mergeMeshMoversIntoOverview,
  type MarketMeshMoversByCode,
} from '../api/market';
import { cacheKeys } from '../cache/cacheKeys';
import { fetchCached, getCached, invalidateCache } from '../cache/queryCache';
import type { MarketOverview } from '../types/market';
import type { MeshSectorFilterState } from '../utils/marketSectorFilters';
import { minCapKeyFromFilters, minCapThresholdsFromYi } from '../utils/marketSectorFilters';
import { useMarketDataCacheEpoch } from './useMarketDataCacheEpoch';

interface UseMarketOverviewResult {
  data: MarketOverview | null;
  /** True while index/benchmark shell has not resolved. */
  loading: boolean;
  /** True while Mesh sector movers are loading/refreshing in the background. */
  sectorsLoading: boolean;
  error: string | null;
  reload: () => void;
}

export function useMarketOverview(
  filters: MeshSectorFilterState,
  options: { loadMeshMovers?: boolean } = {},
): UseMarketOverviewResult {
  const loadMeshMovers = options.loadMeshMovers ?? true;
  const cacheEpoch = useMarketDataCacheEpoch();
  const benchmarksKey = cacheKeys.marketBenchmarks();
  const capKey = useMemo(() => minCapKeyFromFilters(filters), [filters]);
  const moversKey = cacheKeys.marketMeshMovers(filters.sectorLimit, filters.days, capKey);

  const [shell, setShell] = useState<MarketOverview | null>(() =>
    getCached<MarketOverview>(benchmarksKey),
  );
  const [movers, setMovers] = useState<MarketMeshMoversByCode | null>(() =>
    loadMeshMovers ? getCached<MarketMeshMoversByCode>(moversKey) : null,
  );
  const [loading, setLoading] = useState(() => !getCached<MarketOverview>(benchmarksKey));
  const [sectorsLoading, setSectorsLoading] = useState(() => {
    if (!loadMeshMovers) return false;
    return !getCached<MarketMeshMoversByCode>(moversKey);
  });
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  const reload = useCallback(() => {
    invalidateCache(benchmarksKey);
    if (loadMeshMovers) invalidateCache(moversKey);
    setTick((n) => n + 1);
  }, [benchmarksKey, moversKey, loadMeshMovers]);

  // Phase 1: indexes / sparklines — gates first paint of Market page.
  useEffect(() => {
    let cancelled = false;
    const cached = getCached<MarketOverview>(benchmarksKey);
    if (cached) {
      setShell(cached);
      setLoading(false);
    } else {
      setLoading(true);
    }
    setError(null);

    fetchCached(benchmarksKey, () => fetchMarketOverview())
      .then((overview) => {
        if (!cancelled) setShell(overview);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          if (!cached) setShell(null);
          setError(err instanceof Error ? err.message : '加载 DojoMesh 数据失败');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [benchmarksKey, tick, cacheEpoch]);

  // Phase 2: Mesh movers — only when the Mesh tab needs them (not on Discovery).
  useEffect(() => {
    if (!loadMeshMovers) {
      setSectorsLoading(false);
      return;
    }

    let cancelled = false;
    const cached = getCached<MarketMeshMoversByCode>(moversKey);
    if (cached) {
      setMovers(cached);
      setSectorsLoading(false);
    } else {
      setMovers(null);
      setSectorsLoading(true);
    }

    const min_cap_by_market = minCapThresholdsFromYi(filters.minCapYi);

    fetchCached(moversKey, () =>
      fetchMarketMeshMovers({
        sector_limit: filters.sectorLimit,
        days: filters.days,
        min_cap_by_market,
      }),
    )
      .then((next) => {
        if (!cancelled) setMovers(next);
      })
      .catch(() => {
        if (!cancelled && !cached) setMovers(null);
      })
      .finally(() => {
        if (!cancelled) setSectorsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [
    loadMeshMovers,
    moversKey,
    filters.days,
    filters.sectorLimit,
    filters.minCapYi,
    tick,
    cacheEpoch,
  ]);

  const data = useMemo(() => {
    if (!shell) return null;
    if (!movers) return shell;
    return mergeMeshMoversIntoOverview(shell, movers);
  }, [shell, movers]);

  return { data, loading, sectorsLoading, error, reload };
}
