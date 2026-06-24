import { useEffect, useState } from 'react';
import { fetchSectorScopePerformance } from '../api/dojoSphere';
import { cacheKeys } from '../cache/cacheKeys';
import { fetchCached, getCached } from '../cache/queryCache';
import type { SectorPathSelection } from '../types/sectorTaxonomy';
import type { SectorLevelKey, SectorPerformanceResponse } from '../types/dojoSphere';

const LEVELS: SectorLevelKey[] = ['L1', 'L2', 'L3'];

export function useSectorScopePerformanceAll(selection: SectorPathSelection | null) {
  const cacheKey = selection ? cacheKeys.sectorScopePerformanceAll(selection) : null;
  const [performanceByLevel, setPerformanceByLevel] = useState<
    Partial<Record<SectorLevelKey, SectorPerformanceResponse>>
  >(() => (cacheKey ? getCached<Partial<Record<SectorLevelKey, SectorPerformanceResponse>>>(cacheKey) ?? {} : {}));
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
    const cached = getCached<Partial<Record<SectorLevelKey, SectorPerformanceResponse>>>(cacheKey);
    if (cached) {
      setPerformanceByLevel(cached);
      setLoading(false);
    } else {
      setLoading(true);
    }
    setError(null);

    fetchCached(cacheKey, () =>
      Promise.all(
        LEVELS.map((scope) =>
          fetchSectorScopePerformance({
            level1Id: selection.level1Id,
            level2Id: selection.level2Id,
            level3Id: selection.level3Id,
            scope,
          }).then((data) => [scope, data] as const),
        ),
      ).then((entries) => Object.fromEntries(entries)),
    )
      .then((data) => {
        if (!cancelled) setPerformanceByLevel(data);
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
  }, [cacheKey, selection?.level1Id, selection?.level2Id, selection?.level3Id]);

  return { performanceByLevel, loading, error };
}
