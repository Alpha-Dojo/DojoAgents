import { useCallback, useEffect, useState } from 'react';
import {
  parseTabHash,
  pushAppTab,
  readTabFromHistory,
  replaceAppTab,
  type AppTab,
} from '../navigation/appTab';

export function useAppTab(initial: AppTab = 'mesh') {
  const [tab, setTabState] = useState<AppTab>(() => {
    return readTabFromHistory() ?? parseTabHash(window.location.hash) ?? initial;
  });

  useEffect(() => {
    if (!readTabFromHistory()) {
      replaceAppTab(initial);
    }
  }, [initial]);

  useEffect(() => {
    const onPopState = () => {
      setTabState(readTabFromHistory() ?? parseTabHash(window.location.hash) ?? 'mesh');
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
