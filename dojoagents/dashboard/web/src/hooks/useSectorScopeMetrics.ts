import { useEffect, useState } from 'react';
import { fetchSectorAnalysis } from '../api/dojoSphere';
import { cacheKeys } from '../cache/cacheKeys';
import { fetchCached, getCached } from '../cache/queryCache';
import type { SectorPathSelection } from '../types/sectorTaxonomy';
import type { SectorScopeMetricsResponse } from '../types/dojoSphere';

export function useSectorScopeMetrics(selection: SectorPathSelection | null) {
  const cacheKey = selection ? cacheKeys.sectorAnalysis(selection) : null;
  const [metrics, setMetrics] = useState<SectorScopeMetricsResponse | null>(() =>
    cacheKey
      ? (getCached<Awaited<ReturnType<typeof fetchSectorAnalysis>>>(cacheKey)?.scopes.L3?.metrics ??
          getCached<Awaited<ReturnType<typeof fetchSectorAnalysis>>>(cacheKey)?.scopes.L2?.metrics ??
          getCached<Awaited<ReturnType<typeof fetchSectorAnalysis>>>(cacheKey)?.scopes.L1?.metrics ??
          null)
      : null,
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
    const cached = getCached<Awaited<ReturnType<typeof fetchSectorAnalysis>>>(cacheKey);
    const cachedMetrics =
      cached?.scopes.L3?.metrics ?? cached?.scopes.L2?.metrics ?? cached?.scopes.L1?.metrics ?? null;
    if (cachedMetrics) {
      setMetrics(cachedMetrics);
      setLoading(false);
    } else {
      setLoading(true);
    }
    setError(null);

    fetchCached(cacheKey, () =>
      fetchSectorAnalysis({
        level1Id: selection.level1Id,
        level2Id: selection.level2Id,
        level3Id: selection.level3Id,
      }),
    )
      .then((data) => {
        if (cancelled) return;
        setMetrics(data.scopes.L3?.metrics ?? data.scopes.L2?.metrics ?? data.scopes.L1?.metrics ?? null);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          if (!cachedMetrics) setMetrics(null);
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
