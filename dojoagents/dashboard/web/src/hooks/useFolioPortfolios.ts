import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import {
  addFolioHolding,
  autoAllocateFolioPortfolio,
  createFolioPortfolio,
  createFolioOrder,
  deleteFolioPortfolio,
  fetchFolioPortfolioDetail,
  fetchFolioPortfolios,
  type FolioPortfolioDetail,
  removeFolioHolding,
  updateFolioPortfolio,
} from '../api/folio';
import { useMarketDataCacheEpoch } from './useMarketDataCacheEpoch';
import { ApiError, parseApiErrorMessage } from '../api/http';
import { FOLIO_UPDATED_EVENT, type FolioUpdatedDetail } from '../navigation/folio_sync';
import {
  readActiveFolioPortfolioId,
  saveActiveFolioPortfolio,
} from '../navigation/folioContext';
import { cacheKeys } from '../cache/cacheKeys';
import { fetchCached, getCached, invalidateCache, invalidateCachePrefix, setCached } from '../cache/queryCache';
import type { FolioAllocationStrategy, FolioCreateOrderPayload, FolioPortfolioConfig } from '../types/folio';
import type { MarketCode } from '../types/market';
import type { FolioPortfolioHoldingsPreview } from '../utils/folioPortfolioSearch';
import { searchPortfoliosClient } from '../utils/folioPortfolioSearch';
import { portfolioAnalysisBenchmarkParam } from '../utils/folioCandidateIndex';
import {
  computeMarketSnapshotsFromDetail,
  emptyMarketSnapshots,
  type FolioMarketSnapshotsByMarket,
} from '../utils/folioPortfolioSnapshot';
import { folioHasNavPerformance } from '../utils/folioNavSeries';

function loadStoredActiveId(): string | null {
  return readActiveFolioPortfolioId();
}

function storeActiveId(id: string, name?: string | null) {
  saveActiveFolioPortfolio(id, name);
}

function hasNavPerformance(detail: FolioPortfolioDetail | null | undefined): boolean {
  return folioHasNavPerformance(detail?.performance);
}

export interface FolioPortfolioListItem {
  id: string;
  name: string;
  subtitle?: string;
  kind: 'manual' | 'agent';
  pinned: boolean;
  todayChange: number | null;
  netValueUsd: number | null;
  marketSnapshots?: FolioMarketSnapshotsByMarket;
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
    candidates: [],
    positions: [],
    holdings: [],
    sharesByTicker: {},
    todayChange: null,
    netValueUsd: null,
    netValueByMarket: { us: 0, cn: 0, hk: 0 },
    costBasisByMarket: { us: 0, cn: 0, hk: 0 },
    kpis: null,
    performance: null,
    orders: [],
  };
}

function mergePortfolioDetail(
  _prev: FolioPortfolioDetail | null | undefined,
  updated: FolioPortfolioDetail,
): FolioPortfolioDetail {
  // Never stitch old NAV/performance onto a fresh API payload.
  return updated;
}

function readCachedPortfolioDetail(
  portfolioId: string,
  benchmarkSymbol: string | null,
): FolioPortfolioDetail | null {
  const apiBenchmark = portfolioAnalysisBenchmarkParam(benchmarkSymbol) ?? null;
  const full = getCached<FolioPortfolioDetail>(
    cacheKeys.folioPortfolio(portfolioId, apiBenchmark),
  );
  if (full?.id === portfolioId) {
    return full;
  }
  const lite = getCached<FolioPortfolioDetail>(cacheKeys.folioPortfolioLite(portfolioId));
  if (lite?.id === portfolioId) {
    return lite;
  }
  return null;
}

function resolveDefaultPortfolioId(rows: FolioPortfolioListItem[]): string {
  const pinned = rows.find((row) => row.pinned);
  if (pinned) return pinned.id;
  return rows[0]?.id ?? '';
}

export function useFolioPortfolios() {
  const cacheEpoch = useMarketDataCacheEpoch();
  const listCacheKey = cacheKeys.folioPortfolios();

  const [listItems, setListItems] = useState<FolioPortfolioListItem[]>([]);
  const listItemsRef = useRef(listItems);
  listItemsRef.current = listItems;
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [creatingPortfolio, setCreatingPortfolio] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const createInFlightRef = useRef(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [benchmarkSymbols, setBenchmarkSymbols] = useState<string[]>([]);

  const [activeId, setActiveIdState] = useState<string>(() => loadStoredActiveId() ?? '');
  const [detail, setDetail] = useState<FolioPortfolioDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [addingTicker, setAddingTicker] = useState(false);
  const [placingOrder, setPlacingOrder] = useState(false);
  const [removingTicker, setRemovingTicker] = useState<string | null>(null);
  const [allocating, setAllocating] = useState(false);
  const [holdingsByPortfolioId, setHoldingsByPortfolioId] = useState<
    Record<string, FolioPortfolioHoldingsPreview[]>
  >({});
  const [snapshotByPortfolioId, setSnapshotByPortfolioId] = useState<
    Record<string, FolioMarketSnapshotsByMarket>
  >({});
  const activeIdRef = useRef(activeId);
  activeIdRef.current = activeId;

  const setActiveId = useCallback((value: string | ((prev: string) => string)) => {
    setActiveIdState((prev) => {
      const next = typeof value === 'function' ? value(prev) : value;
      const name = listItemsRef.current.find((item) => item.id === next)?.name;
      storeActiveId(next, name);
      return next;
    });
  }, []);

  useLayoutEffect(() => {
    setDetail((prev) => (prev && prev.id !== activeId ? null : prev));
  }, [activeId]);

  useEffect(() => {
    if (!activeId) return;
    const name =
      detail?.id === activeId
        ? detail.name
        : listItems.find((item) => item.id === activeId)?.name;
    if (name) {
      storeActiveId(activeId, name);
    }
  }, [activeId, detail?.id, detail?.name, listItems]);

  useEffect(() => {
    let cancelled = false;
    setListLoading(true);
    setListError(null);

    fetchCached(listCacheKey, () => fetchFolioPortfolios().then((rows) => rows.map(mapSummary)))
      .then((rows) => {
        if (cancelled) return;
        setListItems(rows);
        setActiveId((prev) => {
          const stored = loadStoredActiveId();
          if (stored && rows.some((row) => row.id === stored)) return stored;
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
  }, [listCacheKey, cacheEpoch]);

  useEffect(() => {
    if (listItems.length === 0) return;

    let cancelled = false;
    for (const item of listItems) {
      const detailCacheKey = cacheKeys.folioPortfolioLite(item.id);
      void fetchFolioPortfolioDetail(item.id, { includePerformance: true })
        .then((response) => {
          if (cancelled || response.id !== item.id) return;
          setCached(detailCacheKey, response);
          setSnapshotByPortfolioId((prev) => ({
            ...prev,
            [item.id]: computeMarketSnapshotsFromDetail(response),
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
    setBenchmarkSymbols([]);
  }, [activeId]);

  const primaryBenchmarkSymbol = benchmarkSymbols[0] ?? null;
  const apiBenchmarkSymbol = portfolioAnalysisBenchmarkParam(primaryBenchmarkSymbol) ?? null;

  useEffect(() => {
    if (!activeId) {
      setDetail(null);
      setDetailLoading(false);
      setDetailError(null);
      return;
    }

    let cancelled = false;
    const detailCacheKey = cacheKeys.folioPortfolio(activeId, apiBenchmarkSymbol);
    const cached = getCached<FolioPortfolioDetail>(detailCacheKey);
    const cachedUsable =
      cached?.id === activeId &&
      hasNavPerformance(cached);

    setDetail((prev) => (prev?.id === activeId ? prev : null));
    setDetailLoading(true);
    setDetailError(null);

    if (cachedUsable) {
      setDetail(cached);
    } else if (cached?.id === activeId) {
      invalidateCache(detailCacheKey);
    }

    void fetchFolioPortfolioDetail(activeId, {
      benchmark: apiBenchmarkSymbol ?? undefined,
      includePerformance: true,
      startDate: cached?.id === activeId ? cached.config?.startDate : undefined,
    })
      .then((response) => {
        if (cancelled || response.id !== activeId) return;
        setCached(detailCacheKey, response);
        setDetail(response);
        setSnapshotByPortfolioId((prev) => ({
          ...prev,
          [response.id]: computeMarketSnapshotsFromDetail(response),
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
  }, [activeId, apiBenchmarkSymbol, cacheEpoch]);

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
        const snapshots =
          item.id === activeId && detail?.id === activeId
            ? computeMarketSnapshotsFromDetail(detail)
            : snapshotByPortfolioId[item.id] ?? emptyMarketSnapshots();
        if (item.id === activeId && detail?.id === activeId) {
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
    [activeId, detail, listItems, snapshotByPortfolioId],
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
    const cached = readCachedPortfolioDetail(updated.id, primaryBenchmarkSymbol);
    const merged = mergePortfolioDetail(cached, updated);
    if (!hasNavPerformance(merged)) {
      invalidateCachePrefix(`folio-portfolio:${merged.id}:`);
    }
    setCached(cacheKeys.folioPortfolio(merged.id, apiBenchmarkSymbol), merged);
    setSnapshotByPortfolioId((prev) => ({
      ...prev,
      [merged.id]: computeMarketSnapshotsFromDetail(merged),
    }));
    setHoldingsByPortfolioId((prev) => ({
      ...prev,
      [merged.id]: merged.holdings.map((holding) => ({
        ticker: holding.ticker,
        name: holding.name,
      })),
    }));
    setListItems((prev) => {
      const summary = mapSummary({
        id: merged.id,
        name: merged.name,
        subtitle: merged.subtitle,
        kind: merged.kind,
        pinned: merged.pinned ?? false,
        today_change: merged.todayChange,
        net_value_usd: merged.netValueUsd,
      });
      const index = prev.findIndex((item) => item.id === merged.id);
      if (index < 0) return [...prev, summary];
      return prev.map((item) => (item.id === merged.id ? { ...item, ...summary } : item));
    });
    if (merged.id !== activeIdRef.current) {
      return;
    }
    setDetail(merged);

    if (!hasNavPerformance(merged)) {
      void fetchFolioPortfolioDetail(merged.id, {
        benchmark: apiBenchmarkSymbol ?? undefined,
        includePerformance: true,
        startDate: merged.config?.startDate,
      })
        .then((response) => {
          if (response.id !== activeIdRef.current) return;
          setCached(cacheKeys.folioPortfolio(response.id, apiBenchmarkSymbol), response);
          setDetail(response);
          setSnapshotByPortfolioId((prev) => ({
            ...prev,
            [response.id]: computeMarketSnapshotsFromDetail(response),
          }));
        })
        .catch(() => {
          // Best-effort; holdings already updated.
        });
    }
  }, [apiBenchmarkSymbol, primaryBenchmarkSymbol]);

  const selectBenchmarkSymbol = useCallback((symbol: string) => {
    setBenchmarkSymbols([symbol]);
  }, []);

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
      } else if (payload.portfolioId && payload.portfolioId === activeIdRef.current) {
        invalidateCachePrefix(`folio-portfolio:${payload.portfolioId}:`);
        void fetchFolioPortfolioDetail(payload.portfolioId, { includePerformance: true })
          .then((response) => commitDetail(response))
          .catch(() => {
            // Best-effort refresh after agent/list sync.
          });
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

  const promotePortfolioToManual = useCallback(
    async (id: string) => {
      try {
        const updated = await updateFolioPortfolio(id, { kind: 'manual' });
        setListItems((prev) =>
          prev.map((item) => (item.id === id ? { ...item, kind: 'manual' } : item)),
        );
        if (detail?.id === id) {
          setDetail((prev) => (prev ? { ...prev, kind: 'manual' } : prev));
        }
        invalidateCache(listCacheKey);
        invalidateCachePrefix(`folio-portfolio:${id}:`);
        void updated;
        setListError(null);
      } catch (err: unknown) {
        setListError(err instanceof Error ? err.message : 'Failed to promote portfolio');
        throw err;
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
        throw err;
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

  const createOrder = useCallback(
    async (id: string, payload: FolioCreateOrderPayload) => {
      setPlacingOrder(true);
      try {
        invalidateCachePrefix(`folio-portfolio:${id}:`);
        const updated = await createFolioOrder(id, payload);
        commitDetail(updated);
        setDetailError(null);
      } catch (err: unknown) {
        setDetailError(parseApiErrorMessage(err, 'Failed to create order'));
        throw err;
      } finally {
        setPlacingOrder(false);
      }
    },
    [commitDetail],
  );

  const autoAllocate = useCallback(
    async (id: string, strategy: FolioAllocationStrategy = 'market_cap') => {
      setAllocating(true);
      try {
        invalidateCachePrefix(`folio-portfolio:${id}:`);
        const updated = await autoAllocateFolioPortfolio(id, undefined, strategy);
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
    benchmarkSymbols,
    setBenchmarkSymbols,
    selectBenchmarkSymbol,
    primaryBenchmarkSymbol,
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
    placingOrder,
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
    promotePortfolioToManual,
    applyOpenDate,
    createPortfolio,
    deletePortfolio,
    addHolding,
    removeHolding,
    createOrder,
    autoAllocate,
  };
}

export type UseFolioPortfoliosResult = ReturnType<typeof useFolioPortfolios>;
