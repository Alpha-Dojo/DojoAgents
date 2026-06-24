import { useEffect, useState } from 'react';
import { fetchSectorScopeMetrics } from '../api/dojoSphere';
import { cacheKeys } from '../cache/cacheKeys';
import { fetchCached, getCached } from '../cache/queryCache';
import type { SectorPathSelection } from '../types/sectorTaxonomy';
import type { SectorScopeMetricsResponse } from '../types/dojoSphere';

export function useSectorScopeMetrics(selection: SectorPathSelection | null) {
  const cacheKey = selection ? cacheKeys.sectorScopeMetrics(selection) : null;
  const [metrics, setMetrics] = useState<SectorScopeMetricsResponse | null>(() =>
    cacheKey ? getCached<SectorScopeMetricsResponse>(cacheKey) : null,
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
    const cached = getCached<SectorScopeMetricsResponse>(cacheKey);
    if (cached) {
      setMetrics(cached);
      setLoading(false);
    } else {
      setLoading(true);
    }
    setError(null);

    fetchCached(cacheKey, () =>
      fetchSectorScopeMetrics({
        level1Id: selection.level1Id,
        level2Id: selection.level2Id,
        level3Id: selection.level3Id,
      }),
    )
      .then((data) => {
        if (!cancelled) setMetrics(data);
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
  }, [cacheKey, selection?.level1Id, selection?.level2Id, selection?.level3Id]);

  return { metrics, loading, error };
}
