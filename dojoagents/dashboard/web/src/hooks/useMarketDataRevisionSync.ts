import { useEffect, useRef } from 'react';
import { fetchMarketDataRevision } from '../api/market';
import {
  applyMarketDataRevision,
  getMarketDataRevision,
  setMarketDataRevision,
} from '../cache/marketDataSync';

const POLL_MS = 5 * 60 * 1000;

async function syncMarketDataRevision(): Promise<void> {
  try {
    const payload = await fetchMarketDataRevision();
    applyMarketDataRevision(payload.revision ?? '');
  } catch {
    // Best-effort background sync.
  }
}

/** Poll backend revision and invalidate frontend market caches when K-line data refreshes. */
export function useMarketDataRevisionSync(enabled = true) {
  const syncingRef = useRef(false);

  useEffect(() => {
    if (!enabled) return;

    const run = () => {
      if (syncingRef.current) return;
      syncingRef.current = true;
      void syncMarketDataRevision().finally(() => {
        syncingRef.current = false;
      });
    };

    void fetchMarketDataRevision()
      .then((payload) => {
        const revision = payload.revision ?? '';
        if (!getMarketDataRevision() && revision) {
          setMarketDataRevision(revision);
        } else {
          applyMarketDataRevision(revision);
        }
      })
      .catch(() => {
        // Ignore initial sync errors; polling will retry.
      });

    const timer = window.setInterval(run, POLL_MS);
    const onVisible = () => {
      if (document.visibilityState === 'visible') {
        run();
      }
    };
    document.addEventListener('visibilitychange', onVisible);

    return () => {
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [enabled]);
}
