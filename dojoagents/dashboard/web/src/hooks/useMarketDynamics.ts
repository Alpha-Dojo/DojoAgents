import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchMarketDynamics } from '../api/market';
import { parseApiErrorMessage } from '../api/http';
import { cacheKeys } from '../cache/cacheKeys';
import { fetchCached, invalidateCachePrefix } from '../cache/queryCache';
import type { MarketDynamicsEvent } from '../types/marketDynamics';
import {
  addCalendarDays,
  mergeSortedEventsById,
  toCalendarDate,
  windowBounds,
} from '../utils/marketDynamicsWindow';
import { useMarketDataCacheEpoch } from './useMarketDataCacheEpoch';

/** Half-window around the selected discovery date (calendar days). */
export const DYNAMICS_WINDOW_RADIUS_DAYS = 7;
/** Extend by this many calendar days when the timeline hits an edge. */
export const DYNAMICS_PREFETCH_CHUNK_DAYS = 7;
const FETCH_LIMIT = 5000;
const LATEST_CACHE_KEY = 'latest';

interface UseMarketDynamicsOptions {
  centerDate?: string;
  windowRadiusDays?: number;
  prefetchChunkDays?: number;
}

interface UseMarketDynamicsResult {
  events: MarketDynamicsEvent[];
  tradingDates: string[];
  datasetStart: string;
  datasetEnd: string;
  loadedStart: string;
  loadedEnd: string;
  hasMoreBefore: boolean;
  hasMoreAfter: boolean;
  loading: boolean;
  loadingMore: boolean;
  error: string | null;
  reload: () => void;
  loadMoreBefore: () => void;
  loadMoreAfter: () => void;
}

async function fetchWindow(startDate: string | null, endDate: string | null) {
  const cacheKey = cacheKeys.marketDynamics(
    startDate || LATEST_CACHE_KEY,
    endDate || LATEST_CACHE_KEY,
    FETCH_LIMIT,
  );
  return fetchCached(cacheKey, () =>
    fetchMarketDynamics({
      limit: FETCH_LIMIT,
      startDate: startDate || undefined,
      endDate: endDate || undefined,
    }),
  );
}

export function useMarketDynamics(
  options: UseMarketDynamicsOptions = {},
): UseMarketDynamicsResult {
  const cacheEpoch = useMarketDataCacheEpoch();
  const centerDate = toCalendarDate(options.centerDate);
  const windowRadiusDays = options.windowRadiusDays ?? DYNAMICS_WINDOW_RADIUS_DAYS;
  const prefetchChunkDays = options.prefetchChunkDays ?? DYNAMICS_PREFETCH_CHUNK_DAYS;

  const [events, setEvents] = useState<MarketDynamicsEvent[]>([]);
  const [tradingDates, setTradingDates] = useState<string[]>([]);
  const [datasetStart, setDatasetStart] = useState('');
  const [datasetEnd, setDatasetEnd] = useState('');
  const [loadedStart, setLoadedStart] = useState('');
  const [loadedEnd, setLoadedEnd] = useState('');
  const [hasMoreBefore, setHasMoreBefore] = useState(false);
  const [hasMoreAfter, setHasMoreAfter] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  const inflightBefore = useRef(false);
  const inflightAfter = useRef(false);
  const loadedStartRef = useRef('');
  const loadedEndRef = useRef('');
  const hasMoreBeforeRef = useRef(false);
  const hasMoreAfterRef = useRef(false);

  useEffect(() => {
    loadedStartRef.current = loadedStart;
  }, [loadedStart]);
  useEffect(() => {
    loadedEndRef.current = loadedEnd;
  }, [loadedEnd]);
  useEffect(() => {
    hasMoreBeforeRef.current = hasMoreBefore;
  }, [hasMoreBefore]);
  useEffect(() => {
    hasMoreAfterRef.current = hasMoreAfter;
  }, [hasMoreAfter]);

  const applyMeta = useCallback(
    (response: Awaited<ReturnType<typeof fetchWindow>>) => {
      if (response.trading_dates?.length) {
        setTradingDates(response.trading_dates);
      }
      if (response.dataset_start) setDatasetStart(response.dataset_start);
      if (response.dataset_end) setDatasetEnd(response.dataset_end);
    },
    [],
  );

  const reload = useCallback(() => {
    invalidateCachePrefix('market-dynamics:');
    setTick((n) => n + 1);
  }, []);

  const hasEventsRef = useRef(false);
  useEffect(() => {
    hasEventsRef.current = events.length > 0;
  }, [events.length]);

  useEffect(() => {
    let cancelled = false;
    const bounds = centerDate
      ? windowBounds(centerDate, windowRadiusDays)
      : { startDate: null as string | null, endDate: null as string | null };

    // After the initial "latest" load, selecting a date already inside the
    // loaded calendar range should only scroll — not refetch/clear.
    if (
      centerDate &&
      loadedStartRef.current &&
      loadedEndRef.current &&
      centerDate >= loadedStartRef.current &&
      centerDate <= loadedEndRef.current &&
      hasEventsRef.current
    ) {
      setLoading(false);
      return () => {
        cancelled = true;
      };
    }

    setLoading(true);
    setError(null);
    if (centerDate) {
      setEvents([]);
      setLoadedStart(bounds.startDate || '');
      setLoadedEnd(bounds.endDate || '');
      loadedStartRef.current = bounds.startDate || '';
      loadedEndRef.current = bounds.endDate || '';
    }

    fetchWindow(bounds.startDate, bounds.endDate)
      .then((response) => {
        if (cancelled) return;
        applyMeta(response);
        setEvents(response.events ?? []);
        setHasMoreBefore(Boolean(response.has_more_before));
        setHasMoreAfter(Boolean(response.has_more_after));
        hasMoreBeforeRef.current = Boolean(response.has_more_before);
        hasMoreAfterRef.current = Boolean(response.has_more_after);
        const start =
          bounds.startDate ||
          toCalendarDate(response.window_start) ||
          toCalendarDate(response.dataset_start) ||
          '';
        const end =
          bounds.endDate ||
          toCalendarDate(response.window_end) ||
          toCalendarDate(response.dataset_end) ||
          '';
        setLoadedStart(start);
        setLoadedEnd(end);
        loadedStartRef.current = start;
        loadedEndRef.current = end;
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setEvents([]);
        setError(parseApiErrorMessage(err, 'Failed to load market dynamics'));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [centerDate, windowRadiusDays, tick, cacheEpoch, applyMeta]);

  const loadMoreBefore = useCallback(() => {
    if (inflightBefore.current || loading || loadingMore) return;
    if (!hasMoreBeforeRef.current || !loadedStartRef.current) return;

    const endDate = addCalendarDays(loadedStartRef.current, -1);
    const startDate = addCalendarDays(loadedStartRef.current, -prefetchChunkDays);
    if (!startDate || !endDate || startDate > endDate) return;

    inflightBefore.current = true;
    setLoadingMore(true);
    setError(null);

    fetchWindow(startDate, endDate)
      .then((response) => {
        applyMeta(response);
        setEvents((prev) => mergeSortedEventsById(prev, response.events ?? []));
        setHasMoreBefore(Boolean(response.has_more_before));
        hasMoreBeforeRef.current = Boolean(response.has_more_before);
        setLoadedStart(startDate);
        loadedStartRef.current = startDate;
      })
      .catch((err: unknown) => {
        setError(parseApiErrorMessage(err, 'Failed to load earlier events'));
      })
      .finally(() => {
        inflightBefore.current = false;
        setLoadingMore(false);
      });
  }, [applyMeta, loading, loadingMore, prefetchChunkDays]);

  const loadMoreAfter = useCallback(() => {
    if (inflightAfter.current || loading || loadingMore) return;
    if (!hasMoreAfterRef.current || !loadedEndRef.current) return;

    const startDate = addCalendarDays(loadedEndRef.current, 1);
    const endDate = addCalendarDays(loadedEndRef.current, prefetchChunkDays);
    if (!startDate || !endDate || startDate > endDate) return;

    inflightAfter.current = true;
    setLoadingMore(true);
    setError(null);

    fetchWindow(startDate, endDate)
      .then((response) => {
        applyMeta(response);
        setEvents((prev) => mergeSortedEventsById(prev, response.events ?? []));
        setHasMoreAfter(Boolean(response.has_more_after));
        hasMoreAfterRef.current = Boolean(response.has_more_after);
        setLoadedEnd(endDate);
        loadedEndRef.current = endDate;
      })
      .catch((err: unknown) => {
        setError(parseApiErrorMessage(err, 'Failed to load later events'));
      })
      .finally(() => {
        inflightAfter.current = false;
        setLoadingMore(false);
      });
  }, [applyMeta, loading, loadingMore, prefetchChunkDays]);

  return {
    events,
    tradingDates,
    datasetStart,
    datasetEnd,
    loadedStart,
    loadedEnd,
    hasMoreBefore,
    hasMoreAfter,
    loading,
    loadingMore,
    error,
    reload,
    loadMoreBefore,
    loadMoreAfter,
  };
}
