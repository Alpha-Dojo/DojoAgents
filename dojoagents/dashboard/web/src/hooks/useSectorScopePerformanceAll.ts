import { useEffect, useState } from 'react';
import { fetchSectorAnalysisBundle, type SectorAnalysisBundle } from '../api/sector';
import { cacheKeys } from '../cache/cacheKeys';
import { fetchCached, getCached } from '../cache/queryCache';
import type { SectorPathSelection } from '../types/sectorTaxonomy';
import type { SectorLevelKey, SectorPerformanceResponse } from '../types/sector';
import { useMarketDataCacheEpoch } from './useMarketDataCacheEpoch';

export function useSectorScopePerformanceAll(selection: SectorPathSelection | null) {
  const cacheEpoch = useMarketDataCacheEpoch();
  const cacheKey = selection ? cacheKeys.sectorAnalysisBundle(selection) : null;
  const [performanceByLevel, setPerformanceByLevel] = useState<
    Partial<Record<SectorLevelKey, SectorPerformanceResponse>>
  >(() => getCached<SectorAnalysisBundle>(cacheKey ?? '')?.performanceByLevel ?? {});
  const [loading, setLoading] = useState(() => (cacheKey ? !getCached(cacheKey) : false));
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!selection || !cacheKey) {
      setPerformanceByLevel({});
      setLoading(false);
      setError(null);
      return;
    }

    let cancelled = false;
    const cached = getCached<SectorAnalysisBundle>(cacheKey);
    if (cached) {
      setPerformanceByLevel(cached.performanceByLevel);
      setLoading(false);
    } else {
      setLoading(true);
    }
    setError(null);

    fetchCached(cacheKey, () =>
      fetchSectorAnalysisBundle({
        level1Id: selection.level1Id,
        level2Id: selection.level2Id,
        level3Id: selection.level3Id,
      }),
    )
      .then((bundle) => {
        if (!cancelled) setPerformanceByLevel(bundle.performanceByLevel);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          if (!cached) setPerformanceByLevel({});
          setError(err instanceof Error ? err.message : 'Failed to load sector performance');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [cacheKey, selection?.level1Id, selection?.level2Id, selection?.level3Id, cacheEpoch]);

  return { performanceByLevel, loading, error };
}
