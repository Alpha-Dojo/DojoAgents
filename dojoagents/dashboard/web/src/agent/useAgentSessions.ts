import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from 'react';
import { AGENT_SESSIONS_STORAGE_KEY } from './agentStorage';
import type {
  AgentChatMessage,
  AgentServerSessionMessage,
  AgentServerSessionSummary,
  AgentServerSessionTurn,
  AgentSession,
  AgentSessionStore,
} from '../types/agent';
import {
  hydrateAgentSessionStore,
  getAgentStorageStatus,
  subscribeAgentStorageStatus,
  syncAgentSessionStore,
} from './agentIndexedDb';
import {
  compareSessionFreshness,
  withFallbackTimeout,
} from './agentIndexedDbPolicy';
import {
  MAX_AGENT_SESSIONS,
  writeSessionStore,
} from './agentStoragePolicy';
import { createRandomId } from '../utils/randomId';
import { fetchAgentSessionMessages, fetchAgentSessions } from '../api/agent';
import {
  appendMissingServerSessions,
  serverMessagesToAgentMessages,
} from './agentServerSessions';

export { AGENT_SESSIONS_STORAGE_KEY, AGENT_DRAFT_STORAGE_KEY } from './agentStorage';

const HYDRATION_INTERACTION_TIMEOUT_MS = 1_500;

function createEmptyStore(): AgentSessionStore {
  return { activeSessionId: null, sessions: [] };
}

function loadStore(): AgentSessionStore {
  try {
    const raw = localStorage.getItem(AGENT_SESSIONS_STORAGE_KEY);
    if (!raw) return createEmptyStore();
    const parsed = JSON.parse(raw) as AgentSessionStore;
    if (!Array.isArray(parsed.sessions)) return createEmptyStore();
    return {
      activeSessionId: parsed.activeSessionId ?? null,
      sessions: parsed.sessions.filter((session) => session && session.id),
    };
  } catch {
    return createEmptyStore();
  }
}

function persistStore(store: AgentSessionStore): void {
  writeSessionStore(localStorage, AGENT_SESSIONS_STORAGE_KEY, store);
}

export function deriveSessionTitle(firstUserMessage: string, fallback = 'New chat'): string {
  const trimmed = firstUserMessage.trim().replace(/\s+/g, ' ');
  if (!trimmed) return fallback;
  return trimmed.length > 28 ? `${trimmed.slice(0, 28)}…` : trimmed;
}

function sortSessions(sessions: AgentSession[]): AgentSession[] {
  return [...sessions].sort((a, b) => b.updatedAt - a.updatedAt);
}

function newSessionId(): string {
  return createRandomId();
}

export function useAgentSessions() {
  const [store, setStore] = useState<AgentSessionStore>(() => loadStore());
  const [indexedDbHydrated, setIndexedDbHydrated] = useState(false);
  const [sessionsReady, setSessionsReady] = useState(false);
  const mutationVersionRef = useRef(0);
  const storageStatus = useSyncExternalStore(
    subscribeAgentStorageStatus,
    getAgentStorageStatus,
    getAgentStorageStatus,
  );

  const markMutation = useCallback(() => {
    mutationVersionRef.current += 1;
  }, []);

  const mergeHydratedIntoCurrent = useCallback(
    (current: AgentSessionStore, hydrated: AgentSessionStore): AgentSessionStore => {
      const hydratedById = new Map(
        hydrated.sessions.map((session) => [session.id, session]),
      );
      return {
        activeSessionId: current.activeSessionId,
        sessions: current.sessions.map((session) => {
          const full = hydratedById.get(session.id);
          return full && compareSessionFreshness(full, session) >= 0 ? full : session;
        }),
      };
    },
    [],
  );

  useEffect(() => {
    persistStore(store);
  }, [store]);

  useEffect(() => {
    let cancelled = false;
    const localFallback = store;
    const hydrationMutationVersion = mutationVersionRef.current;
    const hydrationPromise = hydrateAgentSessionStore(localFallback);
    void withFallbackTimeout(
      hydrationPromise,
      localFallback,
      HYDRATION_INTERACTION_TIMEOUT_MS,
    ).then(() => {
      if (!cancelled) setSessionsReady(true);
    });
    void (async () => {
      const hydrated = await hydrationPromise;
      if (cancelled) return;
      setStore((current) => {
        if (mutationVersionRef.current === hydrationMutationVersion) return hydrated;
        return mergeHydratedIntoCurrent(current, hydrated);
      });
      setIndexedDbHydrated(true);
      setSessionsReady(true);
    })();
    return () => {
      cancelled = true;
    };
    // Initial hydration must use the exact synchronous fallback from first render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mergeHydratedIntoCurrent]);

  useEffect(() => {
    if (!indexedDbHydrated) return;
    void syncAgentSessionStore(store);
  }, [indexedDbHydrated, store]);

  useEffect(() => {
    if (!indexedDbHydrated) return;
    let cancelled = false;
    void (async () => {
      const serverSessions: AgentServerSessionSummary[] = [];
      let cursor: string | undefined;
      do {
        const result = await fetchAgentSessions(50, cursor);
        serverSessions.push(...result.sessions);
        cursor = result.next_cursor ?? undefined;
      } while (cursor);
      if (cancelled) return;
      setStore((current) => ({
        ...current,
        sessions: appendMissingServerSessions(current.sessions, serverSessions),
      }));
    })().catch(() => {
      // Local sessions remain fully usable when the server list is unavailable.
    });
    return () => {
      cancelled = true;
    };
  }, [indexedDbHydrated]);

  const activeSession = useMemo(
    () => store.sessions.find((session) => session.id === store.activeSessionId) ?? null,
    [store.activeSessionId, store.sessions],
  );

  const createSession = useCallback((modelId: string, title = '') => {
    markMutation();
    const now = Date.now();
    const session: AgentSession = {
      id: newSessionId(),
      title,
      modelId,
      messages: [],
      createdAt: now,
      updatedAt: now,
      revision: 1,
    };
    setStore((prev) => ({
      activeSessionId: session.id,
      sessions: sortSessions([session, ...prev.sessions]).slice(0, MAX_AGENT_SESSIONS),
    }));
    return session.id;
  }, [markMutation]);

  const selectSession = useCallback((sessionId: string) => {
    markMutation();
    setStore((prev) => {
      if (!prev.sessions.some((session) => session.id === sessionId)) {
        return prev;
      }
      return { ...prev, activeSessionId: sessionId };
    });
  }, [markMutation]);

  const hydrateSessionMessages = useCallback(async (sessionId: string) => {
    const session = store.sessions.find((item) => item.id === sessionId);
    if (
      !session ||
      session.source !== 'server' ||
      (session.messagesHydrated !== false && session.activityHydrationVersion === 7)
    ) return;
    const serverMessages: AgentServerSessionMessage[] = [];
    let turns: AgentServerSessionTurn[] = [];
    let offset: number | undefined = 0;
    do {
      const response = await fetchAgentSessionMessages(sessionId, 200, offset);
      if (response.turns?.length) turns = response.turns;
      serverMessages.push(...response.messages);
      offset = response.next_offset ?? undefined;
    } while (offset !== undefined);
    const hydratedMessages = serverMessagesToAgentMessages({
      session_id: sessionId,
      agent_id: '',
      messages: serverMessages,
      next_offset: null,
      turns,
    });
    markMutation();
    setStore((current) => ({
      ...current,
      sessions: current.sessions.map((item) =>
        item.id === sessionId
          ? {
              ...item,
              messages: hydratedMessages,
              messagesHydrated: true,
              activityHydrated: true,
              activityHydrationVersion: 7,
              revision: (item.revision ?? 0) + 1,
            }
          : item,
      ),
    }));
  }, [markMutation, store.sessions]);

  const ensureActiveSession = useCallback(
    (modelId: string) => {
      if (activeSession) {
        return activeSession.id;
      }
      return createSession(modelId);
    },
    [activeSession, createSession],
  );

  const replaceSessionMessages = useCallback(
    (sessionId: string, messages: AgentChatMessage[], modelId?: string) => {
      markMutation();
      setStore((prev) => {
        const now = Date.now();
        const firstUser = messages.find((message) => message.role === 'user');
        const sessions = prev.sessions.map((session) => {
          if (session.id !== sessionId) return session;
          return {
            ...session,
            messages,
            modelId: modelId ?? session.modelId,
            title:
              !session.title.trim() && firstUser
                ? deriveSessionTitle(firstUser.content)
                : session.title,
            updatedAt: now,
            revision: (session.revision ?? 0) + 1,
          };
        });
        return { ...prev, sessions: sortSessions(sessions) };
      });
    },
    [markMutation],
  );

  const deleteSession = useCallback((sessionId: string) => {
    markMutation();
    setStore((prev) => {
      const sessions = prev.sessions.filter((session) => session.id !== sessionId);
      const activeSessionId =
        prev.activeSessionId === sessionId ? (sessions[0]?.id ?? null) : prev.activeSessionId;
      return { activeSessionId, sessions };
    });
  }, [markMutation]);

  const reloadFromStorage = useCallback(() => {
    const localFallback = loadStore();
    const reloadMutationVersion = mutationVersionRef.current;
    void (async () => {
      const hydrated = await hydrateAgentSessionStore(localFallback);
      setStore((current) =>
        mutationVersionRef.current === reloadMutationVersion
          ? hydrated
          : mergeHydratedIntoCurrent(current, hydrated),
      );
    })();
  }, [mergeHydratedIntoCurrent]);

  return {
    sessionsHydrated: sessionsReady,
    storageStatus,
    sessions: store.sessions,
    activeSessionId: store.activeSessionId,
    activeSession,
    createSession,
    selectSession,
    hydrateSessionMessages,
    ensureActiveSession,
    replaceSessionMessages,
    deleteSession,
    reloadFromStorage,
  };
}
