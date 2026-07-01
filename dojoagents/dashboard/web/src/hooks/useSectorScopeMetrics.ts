import { useEffect, useState } from 'react';
import { fetchSectorAnalysisBundle, type SectorAnalysisBundle } from '../api/sector';
import { cacheKeys } from '../cache/cacheKeys';
import { fetchCached, getCached } from '../cache/queryCache';
import type { SectorPathSelection } from '../types/sectorTaxonomy';
import type { SectorScopeMetricsResponse } from '../types/sector';
import { useMarketDataCacheEpoch } from './useMarketDataCacheEpoch';

export function useSectorScopeMetrics(selection: SectorPathSelection | null) {
  const cacheEpoch = useMarketDataCacheEpoch();
  const cacheKey = selection ? cacheKeys.sectorAnalysisBundle(selection) : null;
  const [metrics, setMetrics] = useState<SectorScopeMetricsResponse | null>(() =>
    getCached<SectorAnalysisBundle>(cacheKey ?? '')?.metrics ?? null,
  );
  const [loading, setLoading] = useState(() => (cacheKey ? !getCached(cacheKey) : false));
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!selection || !cacheKey) {
      setMetrics(null);
      setLoading(false);
      setError(null);
      return;
    }

    let cancelled = false;
    const cached = getCached<SectorAnalysisBundle>(cacheKey);
    if (cached) {
      setMetrics(cached.metrics);
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
        if (!cancelled) setMetrics(bundle.metrics);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          if (!cached) setMetrics(null);
          setError(err instanceof Error ? err.message : 'Failed to load sector metrics');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [cacheKey, selection?.level1Id, selection?.level2Id, selection?.level3Id, cacheEpoch]);

  return { metrics, loading, error };
}
