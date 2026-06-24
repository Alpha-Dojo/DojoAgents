import { useEffect, useState } from 'react';
import { fetchSectorAnalysis } from '../api/dojoSphere';
import { cacheKeys } from '../cache/cacheKeys';
import { fetchCached, getCached } from '../cache/queryCache';
import type { SectorPathSelection } from '../types/sectorTaxonomy';
import type { SectorLevelKey, SectorPerformanceResponse } from '../types/dojoSphere';

const LEVELS: SectorLevelKey[] = ['L1', 'L2', 'L3'];

export function useSectorScopePerformanceAll(selection: SectorPathSelection | null) {
  const cacheKey = selection ? cacheKeys.sectorAnalysis(selection) : null;
  const [performanceByLevel, setPerformanceByLevel] = useState<
    Partial<Record<SectorLevelKey, SectorPerformanceResponse>>
  >(() => {
    const cached = cacheKey ? getCached<Awaited<ReturnType<typeof fetchSectorAnalysis>>>(cacheKey) : null;
    if (!cached) return {};
    return Object.fromEntries(
      LEVELS.flatMap((scope) => (cached.scopes[scope]?.performance ? [[scope, cached.scopes[scope]!.performance]] : [])),
    ) as Partial<Record<SectorLevelKey, SectorPerformanceResponse>>;
  });
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
    const cached = getCached<Awaited<ReturnType<typeof fetchSectorAnalysis>>>(cacheKey);
    const cachedPerformance = cached
      ? (Object.fromEntries(
          LEVELS.flatMap((scope) => (cached.scopes[scope]?.performance ? [[scope, cached.scopes[scope]!.performance]] : [])),
        ) as Partial<Record<SectorLevelKey, SectorPerformanceResponse>>)
      : null;
    if (cachedPerformance) {
      setPerformanceByLevel(cachedPerformance);
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
        setPerformanceByLevel(
          Object.fromEntries(
            LEVELS.flatMap((scope) => (data.scopes[scope]?.performance ? [[scope, data.scopes[scope]!.performance]] : [])),
          ) as Partial<Record<SectorLevelKey, SectorPerformanceResponse>>,
        );
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          if (!cachedPerformance) setPerformanceByLevel({});
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
