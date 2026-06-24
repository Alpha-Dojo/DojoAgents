import { useEffect, useState } from 'react';
import { fetchCoreTickerQuote, type CoreTickerQuoteResponse } from '../api/dojoCore';
import { cacheKeys } from '../cache/cacheKeys';
import { fetchCached, getCached } from '../cache/queryCache';
import type { CoreTickerContext } from '../navigation/coreContext';
import type { CoreQuoteSnapshot } from '../types/dojoCore';

function mapQuoteResponse(raw: CoreTickerQuoteResponse): CoreQuoteSnapshot {
  return {
    price: raw.last_price,
    change: raw.change,
    changePercent: raw.change_percent,
    currency: raw.currency ?? 'USD',
  };
}

export function useCoreQuote(ctx: CoreTickerContext | null) {
  const cacheKey = ctx?.ticker ? cacheKeys.coreTickerQuote(ctx.market, ctx.ticker) : null;
  const requestKey = ctx?.ticker ? `${ctx.market ?? ''}:${ctx.ticker}` : '';

  const [quote, setQuote] = useState<CoreQuoteSnapshot | null>(() => {
    const cached = cacheKey ? getCached<CoreTickerQuoteResponse>(cacheKey) : null;
    return cached ? mapQuoteResponse(cached) : null;
  });
  const [detail, setDetail] = useState<CoreTickerQuoteResponse | null>(() =>
    cacheKey ? getCached<CoreTickerQuoteResponse>(cacheKey) : null,
  );
  const [loading, setLoading] = useState(() => (cacheKey ? !getCached(cacheKey) : false));
  const [error, setError] = useState<string | null>(null);
  const [loadedKey, setLoadedKey] = useState(() => (cacheKey && getCached(cacheKey) ? requestKey : ''));

  useEffect(() => {
    if (!ctx?.ticker || !cacheKey) {
      setQuote(null);
      setDetail(null);
      setLoadedKey('');
      setError(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    const cached = getCached<CoreTickerQuoteResponse>(cacheKey);
    if (cached) {
      setQuote(mapQuoteResponse(cached));
      setDetail(cached);
      setLoadedKey(`${ctx.market ?? ''}:${cached.ticker}`);
      setLoading(false);
    } else {
      setQuote(null);
      setDetail(null);
      setLoadedKey('');
      setLoading(true);
    }
    setError(null);

    fetchCached(cacheKey, () =>
      fetchCoreTickerQuote({
        ticker: ctx.ticker,
        market: ctx.market,
      }),
    )
      .then((response) => {
        if (cancelled) return;
        setQuote(mapQuoteResponse(response));
        setDetail(response);
        setLoadedKey(`${ctx.market ?? ''}:${response.ticker}`);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (!cached) {
          setQuote(null);
          setDetail(null);
          setLoadedKey('');
        }
        setError(err instanceof Error ? err.message : 'Failed to load quote');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [ctx?.ticker, ctx?.market, cacheKey]);

  const ready = !loading && loadedKey === requestKey && requestKey !== '';

  return { quote, detail, loading, error, ready, requestKey };
}
