import { useEffect, useState } from 'react';
import { fetchSectorScopePerformance } from '../api/sector';
import type { SectorPathSelection } from '../types/sectorTaxonomy';
import type { SectorLevelKey, SectorPerformanceResponse } from '../types/sector';

export function useSectorScopePerformance(
  selection: SectorPathSelection | null,
  scope: SectorLevelKey,
) {
  const [performance, setPerformance] = useState<SectorPerformanceResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!selection) {
      setPerformance(null);
      setError(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    fetchSectorScopePerformance({
      level1Id: selection.level1Id,
      level2Id: selection.level2Id,
      level3Id: selection.level3Id,
      scope,
    })
      .then((data) => {
        if (!cancelled) setPerformance(data);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setPerformance(null);
          setError(err instanceof Error ? err.message : 'Failed to load sector performance');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [selection?.level1Id, selection?.level2Id, selection?.level3Id, scope]);

  return { performance, loading, error };
}
