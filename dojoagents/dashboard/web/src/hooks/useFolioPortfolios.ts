import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  addFolioHolding,
  autoAllocateFolioPortfolio,
  createFolioPortfolio,
  deleteFolioPortfolio,
  fetchFolioPortfolioDetail,
  fetchFolioPortfolios,
  type FolioPortfolioDetail,
  updateFolioPortfolio,
} from '../api/dojoFolio';
import { ApiError } from '../api/http';
import { cacheKeys } from '../cache/cacheKeys';
import { fetchCached, getCached, invalidateCache, invalidateCachePrefix } from '../cache/queryCache';
import type { FolioPortfolioConfig } from '../types/dojoFolio';
import type { MarketCode } from '../types/dojoMesh';
import type { FolioPortfolioHoldingsPreview } from '../utils/folioPortfolioSearch';
import { searchPortfoliosClient } from '../utils/folioPortfolioSearch';

export interface FolioPortfolioListItem {
  id: string;
  name: string;
  subtitle?: string;
  kind: 'manual' | 'agent';
  todayChange: number | null;
  netValueUsd: number | null;
}

function mapSummary(raw: {
  id: string;
  name: string;
  subtitle?: string | null;
  kind: 'manual' | 'agent';
  today_change?: number | null;
  net_value_usd?: number | null;
}): FolioPortfolioListItem {
  return {
    id: raw.id,
    name: raw.name,
    subtitle: raw.subtitle ?? undefined,
    kind: raw.kind,
    todayChange: raw.today_change ?? null,
    netValueUsd: raw.net_value_usd ?? null,
  };
}

function emptyDetail(id: string, name: string): FolioPortfolioDetail {
  return {
    id,
    name,
    subtitle: undefined,
    kind: 'manual',
    config: null,
    holdings: [],
    sharesByTicker: {},
    todayChange: null,
    netValueUsd: null,
    netValueByMarket: { us: 0, sh: 0, hk: 0 },
    kpis: null,
    performance: null,
  };
}

export function useFolioPortfolios() {
  const listCacheKey = cacheKeys.folioPortfolios();

  const [listItems, setListItems] = useState<FolioPortfolioListItem[]>([]);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

  const [activeId, setActiveId] = useState<string>('');
  const [detail, setDetail] = useState<FolioPortfolioDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [addingTicker, setAddingTicker] = useState(false);
  const [holdingsByPortfolioId, setHoldingsByPortfolioId] = useState<
    Record<string, FolioPortfolioHoldingsPreview[]>
  >({});

  useEffect(() => {
    let cancelled = false;
    setListLoading(true);
    setListError(null);

    fetchCached(listCacheKey, () => fetchFolioPortfolios().then((rows) => rows.map(mapSummary)))
      .then((rows) => {
        if (cancelled) return;
        setListItems(rows);
        setActiveId((prev) => {
          if (prev && rows.some((row) => row.id === prev)) return prev;
          return rows[0]?.id ?? '';
        });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          invalidateCache(listCacheKey);
          invalidateCachePrefix('folio-portfolio:');
          setListItems([]);
          setActiveId('');
          setDetail(null);
          setHoldingsByPortfolioId({});
          return;
        }
        setListError(err instanceof Error ? err.message : 'Failed to load portfolios');
        setListItems([]);
        setActiveId('');
      })
      .finally(() => {
        if (!cancelled) setListLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [listCacheKey]);

  useEffect(() => {
    if (!activeId) {
      setDetail(null);
      setDetailLoading(false);
      setDetailError(null);
      return;
    }

    let cancelled = false;
    const detailCacheKey = cacheKeys.folioPortfolio(activeId);
    const cached = getCached<FolioPortfolioDetail>(detailCacheKey);

    if (cached) {
      setDetail(cached);
      setDetailLoading(false);
    } else {
      setDetail(null);
      setDetailLoading(true);
    }
    setDetailError(null);

    fetchCached(detailCacheKey, () => fetchFolioPortfolioDetail(activeId))
      .then((response) => {
        if (cancelled) return;
        setDetail(response);
        setHoldingsByPortfolioId((prev) => ({
          ...prev,
          [response.id]: response.holdings.map((holding) => ({
            ticker: holding.ticker,
            name: holding.name,
          })),
        }));
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (!cached) setDetail(null);
        if (!(err instanceof ApiError && (err.status === 404 || err.status === 501))) {
          setDetailError(err instanceof Error ? err.message : 'Failed to load portfolio');
        }
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [activeId]);

  const activePortfolio = useMemo(() => {
    if (!activeId) return null;
    if (detail?.id === activeId) return detail;
    const summary = listItems.find((item) => item.id === activeId);
    if (!summary) return null;
    return emptyDetail(summary.id, summary.name);
  }, [activeId, detail, listItems]);

  const portfolios = useMemo(
    () =>
      listItems.map((item) => {
        if (detail?.id === item.id) {
          return {
            ...item,
            todayChange: detail.todayChange,
            netValueUsd: detail.netValueUsd,
          };
        }
        return item;
      }),
    [detail, listItems],
  );

  const visiblePortfolios = useMemo(() => {
    if (!searchQuery.trim()) return portfolios;
    const hits = searchPortfoliosClient(searchQuery, portfolios, holdingsByPortfolioId);
    const hitIds = new Set(hits.map((hit) => hit.portfolioId));
    return portfolios.filter((item) => hitIds.has(item.id));
  }, [portfolios, searchQuery, holdingsByPortfolioId]);

  const nextPortfolioName = useCallback(() => {
    const existing = new Set(listItems.map((item) => item.name));
    for (let index = 0; index < 1000; index += 1) {
      const candidate = `组合 ${String.fromCharCode(65 + (index % 26))}${index >= 26 ? index - 25 : ''}`;
      if (!existing.has(candidate)) return candidate;
    }
    return `组合 ${Date.now()}`;
  }, [listItems]);

  const renamePortfolio = useCallback(
    async (id: string, name: string) => {
      const trimmed = name.trim();
      if (!trimmed) return;
      setListItems((prev) =>
        prev.map((item) => (item.id === id ? { ...item, name: trimmed } : item)),
      );
      if (detail?.id === id) {
        setDetail((prev) => (prev ? { ...prev, name: trimmed } : prev));
      }
      try {
        const updated = await updateFolioPortfolio(id, { name: trimmed });
        setDetail(updated);
      } catch {
        // Local rename retained; backend sync when API is available.
      }
    },
    [detail?.id],
  );

  const applyPortfolioConfig = useCallback(
    async (id: string, config: FolioPortfolioConfig) => {
      try {
        const updated = await updateFolioPortfolio(id, { config });
        setDetail(updated);
      } catch {
        setDetail((prev) => (prev && prev.id === id ? { ...prev, config } : prev));
      }
    },
    [],
  );

  const applyShareOverrides = useCallback(
    async (
      id: string,
      sharesByTicker: Record<string, number>,
      manualSharesByTicker?: Record<string, boolean>,
    ) => {
      try {
        const updated = await updateFolioPortfolio(id, {
          shares_by_ticker: sharesByTicker,
          manual_shares_by_ticker: manualSharesByTicker,
        });
        invalidateCache(cacheKeys.folioPortfolio(id));
        setDetail(updated);
      } catch {
        setDetail((prev) =>
          prev && prev.id === id ? { ...prev, sharesByTicker: { ...sharesByTicker } } : prev,
        );
      }
    },
    [],
  );

  const applyOpenDate = useCallback(async (id: string, ticker: string, openDate: string | null) => {
    try {
      const updated = await updateFolioPortfolio(id, {
        open_date_by_ticker: { [ticker]: openDate },
      });
      invalidateCache(cacheKeys.folioPortfolio(id));
      setDetail(updated);
      setDetailError(null);
    } catch (err: unknown) {
      setDetailError(err instanceof Error ? err.message : 'Failed to update open date');
    }
  }, []);

  const createPortfolio = useCallback(async () => {
    const fallbackName = nextPortfolioName();
    try {
      const created = await createFolioPortfolio(fallbackName);
      invalidateCache(listCacheKey);
      const summary = mapSummary({
        id: created.id,
        name: created.name,
        subtitle: created.subtitle,
        kind: created.kind,
        today_change: created.todayChange,
        net_value_usd: created.netValueUsd,
      });
      setListItems((prev) => [...prev, summary]);
      setActiveId(created.id);
      setDetail(created);
      setListError(null);
    } catch (err: unknown) {
      setListError(err instanceof Error ? err.message : 'Failed to create portfolio');
    }
  }, [listCacheKey, nextPortfolioName]);

  const deletePortfolio = useCallback(
    async (id: string) => {
      try {
        await deleteFolioPortfolio(id);
        invalidateCache(listCacheKey);
        invalidateCache(cacheKeys.folioPortfolio(id));
        setListItems((prev) => {
          const next = prev.filter((item) => item.id !== id);
          setActiveId((current) => (current === id ? next[0]?.id ?? '' : current));
          return next;
        });
        setHoldingsByPortfolioId((prev) => {
          const next = { ...prev };
          delete next[id];
          return next;
        });
        if (detail?.id === id) {
          setDetail(null);
        }
        setListError(null);
      } catch (err: unknown) {
        setListError(err instanceof Error ? err.message : 'Failed to delete portfolio');
      }
    },
    [detail?.id, listCacheKey],
  );

  const addHolding = useCallback(
    async (id: string, ticker: string, market: MarketCode) => {
      setAddingTicker(true);
      try {
        const updated = await addFolioHolding(id, { ticker, market });
        invalidateCache(cacheKeys.folioPortfolio(id));
        setDetail(updated);
        setHoldingsByPortfolioId((prev) => ({
          ...prev,
          [id]: updated.holdings.map((holding) => ({
            ticker: holding.ticker,
            name: holding.name,
          })),
        }));
        setDetailError(null);
      } catch (err: unknown) {
        setDetailError(err instanceof Error ? err.message : 'Failed to add holding');
      } finally {
        setAddingTicker(false);
      }
    },
    [],
  );

  const autoAllocate = useCallback(async (id: string, market?: MarketCode) => {
    setDetailLoading(true);
    try {
      const updated = await autoAllocateFolioPortfolio(id, market);
      invalidateCache(cacheKeys.folioPortfolio(id));
      setDetail(updated);
      setDetailError(null);
    } catch (err: unknown) {
      setDetailError(err instanceof Error ? err.message : 'Failed to auto allocate');
    } finally {
      setDetailLoading(false);
    }
  }, []);

  return {
    portfolios: visiblePortfolios,
    allPortfolios: portfolios,
    holdingsByPortfolioId,
    searchQuery,
    setSearchQuery,
    activePortfolio,
    activeId,
    setActiveId,
    listLoading,
    listError,
    detailLoading,
    detailError,
    addingTicker,
    renamePortfolio,
    applyPortfolioConfig,
    applyShareOverrides,
    applyOpenDate,
    createPortfolio,
    deletePortfolio,
    addHolding,
    autoAllocate,
  };
}

export type UseFolioPortfoliosResult = ReturnType<typeof useFolioPortfolios>;
