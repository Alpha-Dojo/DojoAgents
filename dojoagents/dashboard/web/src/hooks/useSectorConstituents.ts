import { useEffect, useState } from 'react';
import { fetchSectorConstituents } from '../api/dojoSphere';
import { cacheKeys, type ConstituentsByMarket } from '../cache/cacheKeys';
import { fetchCached, getCached } from '../cache/queryCache';
import type { MarketCode } from '../types/dojoMesh';
import type { SectorLevelKey } from '../types/dojoSphere';
import type { SectorPathSelection } from '../types/sectorTaxonomy';

const MARKETS: MarketCode[] = ['us', 'sh', 'hk'];

const EMPTY_BY_MARKET: ConstituentsByMarket = {
  us: [],
  sh: [],
  hk: [],
};

export function useSectorConstituents(
  selection: SectorPathSelection | null,
  scope: SectorLevelKey,
) {
  const cacheKey = selection ? cacheKeys.sectorConstituents(selection, scope) : null;
  const [byMarket, setByMarket] = useState<ConstituentsByMarket>(() =>
    cacheKey ? getCached<ConstituentsByMarket>(cacheKey) ?? EMPTY_BY_MARKET : EMPTY_BY_MARKET,
  );
  const [loading, setLoading] = useState(() => (cacheKey ? !getCached(cacheKey) : false));
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!selection || !cacheKey) {
      setByMarket(EMPTY_BY_MARKET);
      setLoading(false);
      setError(null);
      return;
    }

    let cancelled = false;
    const cached = getCached<ConstituentsByMarket>(cacheKey);
    if (cached) {
      setByMarket(cached);
      setLoading(false);
    } else {
      setLoading(true);
    }
    setError(null);

    const params = {
      level1Id: selection.level1Id,
      level2Id: selection.level2Id,
      level3Id: selection.level3Id,
      scope,
    };

    fetchCached(cacheKey, () =>
      Promise.all(MARKETS.map((market) => fetchSectorConstituents({ ...params, market }))).then(
        (responses) => {
          const next = { ...EMPTY_BY_MARKET };
          for (const response of responses) {
            const market = response.market;
            if (market) next[market] = response.items;
          }
          return next;
        },
      ),
    )
      .then((data) => {
        if (!cancelled) setByMarket(data);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          if (!cached) setByMarket(EMPTY_BY_MARKET);
          setError(err instanceof Error ? err.message : 'Failed to load constituents');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [cacheKey, selection?.level1Id, selection?.level2Id, selection?.level3Id, scope]);

  return { byMarket, loading, error };
}
