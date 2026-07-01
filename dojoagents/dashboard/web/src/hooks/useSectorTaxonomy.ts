import { useEffect, useState } from 'react';
import { fetchSectorTaxonomy } from '../api/sector';
import { cacheKeys } from '../cache/cacheKeys';
import { fetchCached, getCached } from '../cache/queryCache';
import type { SectorTaxonomyDocument } from '../types/sectorTaxonomy';
import { useMarketDataCacheEpoch } from './useMarketDataCacheEpoch';

const CACHE_KEY = cacheKeys.sectorTaxonomy();

export function useSectorTaxonomy() {
  const cacheEpoch = useMarketDataCacheEpoch();
  const [taxonomy, setTaxonomy] = useState<SectorTaxonomyDocument | null>(
    () => getCached<SectorTaxonomyDocument>(CACHE_KEY),
  );
  const [loading, setLoading] = useState(() => !getCached<SectorTaxonomyDocument>(CACHE_KEY));
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const cached = getCached<SectorTaxonomyDocument>(CACHE_KEY);
    if (cached) {
      setTaxonomy(cached);
      setLoading(false);
    } else {
      setLoading(true);
    }

    fetchCached(CACHE_KEY, fetchSectorTaxonomy)
      .then((data) => {
        if (!cancelled) {
          setTaxonomy(data);
          setError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          if (!cached) setTaxonomy(null);
          setError(err instanceof Error ? err.message : 'Failed to load sector taxonomy');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [cacheEpoch]);

  return { taxonomy, loading, error };
}
