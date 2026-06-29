import { useCallback, useEffect, useState } from 'react';
import {
  pushAppTab,
  readTabFromHistory,
  replaceAppTab,
  resolveTabFromLocation,
  shouldRewriteLegacyHash,
  type AppTab,
} from '../navigation/appTab';

export function useAppTab(initial: AppTab = 'folio') {
  const [tab, setTabState] = useState<AppTab>(() => resolveTabFromLocation(initial));

  useEffect(() => {
    const resolved = resolveTabFromLocation(initial);
    setTabState(resolved);
    if (shouldRewriteLegacyHash(window.location.hash) || readTabFromHistory() === null) {
      replaceAppTab(resolved);
    }
  }, [initial]);

  useEffect(() => {
    const onPopState = () => {
      setTabState(resolveTabFromLocation('folio'));
    };
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  const setTab = useCallback((next: AppTab) => {
    setTabState(next);
    pushAppTab(next);
  }, []);

  return { tab, setTab };
}
