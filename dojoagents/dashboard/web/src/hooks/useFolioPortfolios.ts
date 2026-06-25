import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  addFolioHolding,
  autoAllocateFolioPortfolio,
  createFolioPortfolio,
  deleteFolioPortfolio,
  fetchFolioPortfolioDetail,
  fetchFolioPortfolios,
  type FolioPortfolioDetail,
  removeFolioHolding,
  updateFolioPortfolio,
} from '../api/dojoFolio';
import { ApiError } from '../api/http';
import { FOLIO_UPDATED_EVENT, type FolioUpdatedDetail } from '../navigation/folio_sync';
import { cacheKeys } from '../cache/cacheKeys';
import { fetchCached, getCached, invalidateCache, invalidateCachePrefix, setCached } from '../cache/queryCache';
import type { FolioAllocationStrategy, FolioPortfolioConfig } from '../types/dojoFolio';
import { FOLIO_MARKETS } from '../types/dojoFolio';
import type { MarketCode } from '../types/dojoMesh';
import type { FolioPortfolioHoldingsPreview } from '../utils/folioPortfolioSearch';
import { searchPortfoliosClient } from '../utils/folioPortfolioSearch';
import {
  computeMarketSnapshots,
  type FolioMarketSnapshot,
  type FolioSnapshotOptions,
} from '../utils/folioPortfolioSnapshot';

function hasNavPerformance(detail: FolioPortfolioDetail | null | undefined): boolean {
  if (!detail?.performance) return false;
  return (['us', 'cn', 'hk'] as MarketCode[]).some(
    (market) => (detail.performance?.seriesByMarket[market]?.length ?? 0) >= 2,
  );
}

export interface FolioPortfolioListItem {
  id: string;
  name: string;
  subtitle?: string;
  kind: 'manual' | 'agent';
  pinned: boolean;
  todayChange: number | null;
  netValueUsd: number | null;
  marketSnapshots?: Partial<Record<MarketCode, FolioMarketSnapshot>>;
}

function mapSummary(raw: {
  id: string;
  name: string;
  subtitle?: string | null;
  kind: 'manual' | 'agent';
  pinned?: boolean;
  today_change?: number | null;
  net_value_usd?: number | null;
}): FolioPortfolioListItem {
  return {
    id: raw.id,
    name: raw.name,
    subtitle: raw.subtitle ?? undefined,
    kind: raw.kind,
    pinned: raw.pinned ?? false,
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
    pinned: false,
    config: null,
    holdings: [],
    sharesByTicker: {},
    todayChange: null,
    netValueUsd: null,
    netValueByMarket: { us: 0, cn: 0, hk: 0 },
    costBasisByMarket: { us: 0, cn: 0, hk: 0 },
    kpis: null,
    performance: null,
  };
}

function snapshotOptionsFromDetail(
  detail: FolioPortfolioDetail,
): FolioSnapshotOptions {
  const returnPctByMarket: Partial<Record<MarketCode, number>> = {};
  for (const market of FOLIO_MARKETS) {
    const pct = detail.performance?.statsByMarket?.[market]?.cumulative_return_pct;
    if (pct != null && !Number.isNaN(pct)) {
      returnPctByMarket[market] = pct;
    }
  }
  return {
    netValueByMarket: detail.netValueByMarket,
    costBasisByMarket: detail.costBasisByMarket,
    returnPctByMarket:
      Object.keys(returnPctByMarket).length > 0 ? returnPctByMarket : undefined,
  };
}

function resolveDefaultPortfolioId(rows: FolioPortfolioListItem[]): string {
  const pinned = rows.find((row) => row.pinned);
  if (pinned) return pinned.id;
  return rows[0]?.id ?? '';
}

export function useFolioPortfolios() {
  const listCacheKey = cacheKeys.folioPortfolios();

  const [listItems, setListItems] = useState<FolioPortfolioListItem[]>([]);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [creatingPortfolio, setCreatingPortfolio] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const createInFlightRef = useRef(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [benchmarkSymbol, setBenchmarkSymbol] = useState<string | null>(null);

  const [activeId, setActiveId] = useState<string>('');
  const [detail, setDetail] = useState<FolioPortfolioDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [addingTicker, setAddingTicker] = useState(false);
  const [removingTicker, setRemovingTicker] = useState<string | null>(null);
  const [allocating, setAllocating] = useState(false);
  const [holdingsByPortfolioId, setHoldingsByPortfolioId] = useState<
    Record<string, FolioPortfolioHoldingsPreview[]>
  >({});
  const [snapshotByPortfolioId, setSnapshotByPortfolioId] = useState<
    Record<string, Partial<Record<MarketCode, FolioMarketSnapshot>>>
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
          return resolveDefaultPortfolioId(rows);
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
    if (listItems.length === 0) return;

    let cancelled = false;
    for (const item of listItems) {
      const detailCacheKey = cacheKeys.folioPortfolioLite(item.id);
      fetchCached(detailCacheKey, () =>
        fetchFolioPortfolioDetail(item.id, { includePerformance: false }),
      )
        .then((response) => {
          if (cancelled) return;
          setSnapshotByPortfolioId((prev) => ({
            ...prev,
            [item.id]: computeMarketSnapshots(
              response.holdings,
              snapshotOptionsFromDetail(response),
            ),
          }));
          setHoldingsByPortfolioId((prev) => ({
            ...prev,
            [item.id]: response.holdings.map((holding) => ({
              ticker: holding.ticker,
              name: holding.name,
            })),
          }));
        })
        .catch(() => {
          // Sidebar stats are best-effort; ignore prefetch failures.
        });
    }

    return () => {
      cancelled = true;
    };
  }, [listItems]);

  useEffect(() => {
    setBenchmarkSymbol(null);
  }, [activeId]);

  useEffect(() => {
    if (!activeId) {
      setDetail(null);
      setDetailLoading(false);
      setDetailError(null);
      return;
    }

    let cancelled = false;
    const detailCacheKey = cacheKeys.folioPortfolio(activeId, benchmarkSymbol);
    const cached = getCached<FolioPortfolioDetail>(detailCacheKey);
    const cachedUsable = cached && hasNavPerformance(cached);

    if (cachedUsable) {
      setDetail(cached);
      setDetailLoading(false);
    } else if (detail?.id !== activeId) {
      setDetail(null);
      setDetailLoading(true);
    } else if (!hasNavPerformance(detail)) {
      setDetailLoading(true);
    }
    setDetailError(null);

    if (cached && !cachedUsable) {
      invalidateCache(detailCacheKey);
    }

    const loadDetail = () =>
      fetchFolioPortfolioDetail(activeId, {
        benchmark: benchmarkSymbol,
        includePerformance: true,
        startDate: cached?.config?.startDate,
      });

    fetchCached(detailCacheKey, loadDetail)
      .then((response) => {
        if (cancelled) return;
        setDetail(response);
        setSnapshotByPortfolioId((prev) => ({
          ...prev,
          [response.id]: computeMarketSnapshots(
            response.holdings,
            snapshotOptionsFromDetail(response),
          ),
        }));
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
        if (!cachedUsable) setDetail(null);
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
  }, [activeId, benchmarkSymbol]);

  const activePortfolio = useMemo(() => {
    if (!activeId) return null;
    if (detail?.id === activeId) return detail;
    const cached = getCached<FolioPortfolioDetail>(
      cacheKeys.folioPortfolio(activeId, benchmarkSymbol),
    );
    if (cached && hasNavPerformance(cached)) return cached;
    const summary = listItems.find((item) => item.id === activeId);
    if (!summary) return null;
    return emptyDetail(summary.id, summary.name);
  }, [activeId, detail, listItems, benchmarkSymbol]);

  const portfolios = useMemo(
    () =>
      listItems.map((item) => {
        const snapshots =
          item.id === detail?.id
            ? computeMarketSnapshots(detail.holdings, snapshotOptionsFromDetail(detail))
            : snapshotByPortfolioId[item.id];
        if (detail?.id === item.id) {
          return {
            ...item,
            todayChange: detail.todayChange,
            netValueUsd: detail.netValueUsd,
            marketSnapshots: snapshots,
          };
        }
        return {
          ...item,
          marketSnapshots: snapshots,
        };
      }),
    [detail, listItems, snapshotByPortfolioId],
  );

  const visiblePortfolios = useMemo(() => {
    const base = !searchQuery.trim()
      ? portfolios
      : (() => {
          const hits = searchPortfoliosClient(searchQuery, portfolios, holdingsByPortfolioId);
          const hitIds = new Set(hits.map((hit) => hit.portfolioId));
          return portfolios.filter((item) => hitIds.has(item.id));
        })();
    return [...base].sort((a, b) => {
      if (a.pinned !== b.pinned) return a.pinned ? -1 : 1;
      return 0;
    });
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

  const commitDetail = useCallback((updated: FolioPortfolioDetail) => {
    setDetail((prev) => {
      const merged =
        hasNavPerformance(updated) || prev?.id !== updated.id || !hasNavPerformance(prev)
          ? updated
          : { ...updated, performance: prev.performance };
      setCached(cacheKeys.folioPortfolio(merged.id, benchmarkSymbol), merged);
      return merged;
    });
    setSnapshotByPortfolioId((prev) => ({
      ...prev,
      [updated.id]: computeMarketSnapshots(
        updated.holdings,
        snapshotOptionsFromDetail(updated),
      ),
    }));
    setHoldingsByPortfolioId((prev) => ({
      ...prev,
      [updated.id]: updated.holdings.map((holding) => ({
        ticker: holding.ticker,
        name: holding.name,
      })),
    }));
    setListItems((prev) => {
      const summary = mapSummary({
        id: updated.id,
        name: updated.name,
        subtitle: updated.subtitle,
        kind: updated.kind,
        pinned: updated.pinned ?? false,
        today_change: updated.todayChange,
        net_value_usd: updated.netValueUsd,
      });
      const index = prev.findIndex((item) => item.id === updated.id);
      if (index < 0) return [...prev, summary];
      return prev.map((item) => (item.id === updated.id ? { ...item, ...summary } : item));
    });
  }, [benchmarkSymbol]);

  const refreshPortfolioList = useCallback(
    async (options?: { selectId?: string; preferAgent?: boolean }) => {
      try {
        invalidateCache(listCacheKey);
        const rows = await fetchFolioPortfolios().then((items) => items.map(mapSummary));
        setListItems(rows);
        setListError(null);

        if (options?.selectId && rows.some((row) => row.id === options.selectId)) {
          setActiveId(options.selectId);
          return;
        }

        if (options?.preferAgent) {
          const agentPortfolio = [...rows].reverse().find((row) => row.kind === 'agent');
          if (agentPortfolio) {
            setActiveId(agentPortfolio.id);
            return;
          }
        }

        setActiveId((prev) =>
          prev && rows.some((row) => row.id === prev) ? prev : resolveDefaultPortfolioId(rows),
        );
      } catch {
        // Keep the current sidebar if refresh fails.
      }
    },
    [listCacheKey],
  );

  useEffect(() => {
    const onFolioUpdated = (event: Event) => {
      const custom = event as CustomEvent<FolioUpdatedDetail>;
      const payload = custom.detail;
      if (!payload) return;

      if (payload.detail) {
        commitDetail(payload.detail);
      }

      const selectId =
        payload.action === 'create' && payload.portfolioId ? payload.portfolioId : undefined;
      void refreshPortfolioList({
        selectId,
        preferAgent: payload.action === 'create' && !selectId,
      });
    };
    window.addEventListener(FOLIO_UPDATED_EVENT, onFolioUpdated);
    return () => window.removeEventListener(FOLIO_UPDATED_EVENT, onFolioUpdated);
  }, [commitDetail, refreshPortfolioList]);

  const applyPortfolioConfig = useCallback(
    async (id: string, config: FolioPortfolioConfig) => {
      try {
        invalidateCachePrefix(`folio-portfolio:${id}:`);
        const updated = await updateFolioPortfolio(id, { config });
        commitDetail(updated);
      } catch {
        setDetail((prev) => (prev && prev.id === id ? { ...prev, config } : prev));
      }
    },
    [commitDetail],
  );

  const applyShareOverrides = useCallback(
    async (id: string, sharesByTicker: Record<string, number>) => {
      try {
        const updated = await updateFolioPortfolio(id, {
          shares_by_ticker: sharesByTicker,
        });
        commitDetail(updated);
      } catch {
        setDetail((prev) =>
          prev && prev.id === id ? { ...prev, sharesByTicker: { ...sharesByTicker } } : prev,
        );
      }
    },
    [commitDetail],
  );

  const toggleSharesLock = useCallback(
    async (id: string, ticker: string, locked: boolean) => {
      try {
        const updated = await updateFolioPortfolio(id, {
          shares_locked_by_ticker: { [ticker]: locked },
        });
        commitDetail(updated);
        setDetailError(null);
      } catch (err: unknown) {
        setDetailError(err instanceof Error ? err.message : 'Failed to update share lock');
      }
    },
    [commitDetail],
  );

  const toggleOpenDateLock = useCallback(
    async (id: string, ticker: string, locked: boolean) => {
      try {
        const updated = await updateFolioPortfolio(id, {
          open_date_locked_by_ticker: { [ticker]: locked },
        });
        commitDetail(updated);
        setDetailError(null);
      } catch (err: unknown) {
        setDetailError(err instanceof Error ? err.message : 'Failed to update open date lock');
      }
    },
    [commitDetail],
  );

  const toggleCostLock = useCallback(
    async (id: string, ticker: string, locked: boolean) => {
      try {
        const updated = await updateFolioPortfolio(id, {
          cost_locked_by_ticker: { [ticker]: locked },
        });
        commitDetail(updated);
        setDetailError(null);
      } catch (err: unknown) {
        setDetailError(err instanceof Error ? err.message : 'Failed to update cost lock');
      }
    },
    [commitDetail],
  );

  const applyCost = useCallback(
    async (id: string, ticker: string, cost: number | null) => {
      try {
        const updated = await updateFolioPortfolio(id, {
          cost_by_ticker: { [ticker]: cost },
        });
        commitDetail(updated);
        setDetailError(null);
      } catch (err: unknown) {
        setDetailError(err instanceof Error ? err.message : 'Failed to update cost');
      }
    },
    [commitDetail],
  );

  const togglePortfolioPin = useCallback(
    async (id: string, pinned: boolean) => {
      setListItems((prev) =>
        prev.map((item) => (item.id === id ? { ...item, pinned } : item)),
      );
      if (pinned) {
        setActiveId(id);
      }
      try {
        const updated = await updateFolioPortfolio(id, { pinned });
        setListItems((prev) =>
          prev.map((item) =>
            item.id === id ? { ...item, pinned: updated.pinned } : item,
          ),
        );
        if (detail?.id === id) {
          setDetail((prev) => (prev ? { ...prev, pinned: updated.pinned } : prev));
        }
        invalidateCache(listCacheKey);
      } catch {
        setListItems((prev) =>
          prev.map((item) => (item.id === id ? { ...item, pinned: !pinned } : item)),
        );
      }
    },
    [detail?.id, listCacheKey],
  );

  const applyOpenDate = useCallback(
    async (id: string, ticker: string, openDate: string | null) => {
      try {
        invalidateCachePrefix(`folio-portfolio:${id}:`);
        const updated = await updateFolioPortfolio(id, {
          open_date_by_ticker: { [ticker]: openDate },
        });
        commitDetail(updated);
        setDetailError(null);
      } catch (err: unknown) {
        setDetailError(err instanceof Error ? err.message : 'Failed to update open date');
      }
    },
    [commitDetail],
  );

  const createPortfolio = useCallback(async () => {
    if (createInFlightRef.current) return;

    createInFlightRef.current = true;
    setCreatingPortfolio(true);
    setCreateError(null);

    const fallbackName = nextPortfolioName();
    try {
      const created = await createFolioPortfolio(fallbackName);
      invalidateCache(listCacheKey);
      const summary = mapSummary({
        id: created.id,
        name: created.name,
        subtitle: created.subtitle,
        kind: created.kind,
        pinned: created.pinned ?? false,
        today_change: created.todayChange,
        net_value_usd: created.netValueUsd,
      });
      setListItems((prev) => [...prev, summary]);
      setActiveId(created.id);
      commitDetail(created);
      setListError(null);
    } catch (err: unknown) {
      const message =
        err instanceof ApiError
          ? typeof err.body === 'object' &&
            err.body !== null &&
            'detail' in err.body &&
            typeof (err.body as { detail: unknown }).detail === 'string'
            ? (err.body as { detail: string }).detail
            : err.message
          : err instanceof Error
            ? err.message
            : 'Failed to create portfolio';
      setCreateError(message);
    } finally {
      createInFlightRef.current = false;
      setCreatingPortfolio(false);
    }
  }, [listCacheKey, nextPortfolioName, commitDetail]);

  const deletePortfolio = useCallback(
    async (id: string) => {
      try {
        await deleteFolioPortfolio(id);
        invalidateCache(listCacheKey);
        invalidateCachePrefix(`folio-portfolio:${id}:`);
        setListItems((prev) => {
          const next = prev.filter((item) => item.id !== id);
          setActiveId((current) =>
            current === id ? resolveDefaultPortfolioId(next) : current,
          );
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
        invalidateCachePrefix(`folio-portfolio:${id}:`);
        const updated = await addFolioHolding(id, { ticker, market });
        commitDetail(updated);
        setDetailError(null);
      } catch (err: unknown) {
        setDetailError(err instanceof Error ? err.message : 'Failed to add holding');
      } finally {
        setAddingTicker(false);
      }
    },
    [commitDetail],
  );

  const removeHolding = useCallback(
    async (id: string, ticker: string, market: MarketCode) => {
      setRemovingTicker(ticker);
      try {
        invalidateCachePrefix(`folio-portfolio:${id}:`);
        const updated = await removeFolioHolding(id, { ticker, market });
        commitDetail(updated);
        setDetailError(null);
      } catch (err: unknown) {
        setDetailError(err instanceof Error ? err.message : 'Failed to remove holding');
      } finally {
        setRemovingTicker(null);
      }
    },
    [commitDetail],
  );

  const autoAllocate = useCallback(
    async (id: string, market?: MarketCode, strategy: FolioAllocationStrategy = 'market_cap') => {
      setAllocating(true);
      try {
        const updated = await autoAllocateFolioPortfolio(id, market, strategy);
        commitDetail(updated);
        setDetailError(null);
      } catch (err: unknown) {
        setDetailError(err instanceof Error ? err.message : 'Failed to auto allocate');
      } finally {
        setAllocating(false);
      }
    },
    [commitDetail],
  );

  return {
    portfolios: visiblePortfolios,
    allPortfolios: portfolios,
    holdingsByPortfolioId,
    searchQuery,
    setSearchQuery,
    benchmarkSymbol,
    setBenchmarkSymbol,
    activePortfolio,
    activeId,
    setActiveId,
    listLoading,
    listError,
    creatingPortfolio,
    createError,
    detailLoading,
    detailError,
    addingTicker,
    removingTicker,
    allocating,
    renamePortfolio,
    applyPortfolioConfig,
    applyShareOverrides,
    toggleSharesLock,
    toggleOpenDateLock,
    toggleCostLock,
    applyCost,
    togglePortfolioPin,
    applyOpenDate,
    createPortfolio,
    deletePortfolio,
    addHolding,
    removeHolding,
    autoAllocate,
  };
}

export type UseFolioPortfoliosResult = ReturnType<typeof useFolioPortfolios>;
