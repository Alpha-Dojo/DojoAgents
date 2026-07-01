import { useEffect, useState } from 'react';
import { MARKET_DATA_REVISION_EVENT } from '../cache/marketDataSync';

/** Bumps when backend market/kline revision changes — add to data hook effect deps. */
export function useMarketDataCacheEpoch(): number {
  const [epoch, setEpoch] = useState(0);

  useEffect(() => {
    const onRevision = () => setEpoch((value) => value + 1);
    window.addEventListener(MARKET_DATA_REVISION_EVENT, onRevision);
    return () => window.removeEventListener(MARKET_DATA_REVISION_EVENT, onRevision);
  }, []);

  return epoch;
}
