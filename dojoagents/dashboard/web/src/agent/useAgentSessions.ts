import { useCallback, useEffect, useMemo, useState } from 'react';
import type { AgentChatMessage, AgentSession, AgentSessionStore } from '../types/agent';

const STORAGE_KEY = 'dojo-agent-sessions-v1';
const MAX_SESSIONS = 50;

function createEmptyStore(): AgentSessionStore {
  return { activeSessionId: null, sessions: [] };
}

function loadStore(): AgentSessionStore {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
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

function persistStore(store: AgentSessionStore) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
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
  return crypto.randomUUID();
}

export function useAgentSessions() {
  const [store, setStore] = useState<AgentSessionStore>(() => loadStore());

  useEffect(() => {
    persistStore(store);
  }, [store]);

  const activeSession = useMemo(
    () => store.sessions.find((session) => session.id === store.activeSessionId) ?? null,
    [store.activeSessionId, store.sessions],
  );

  const createSession = useCallback((modelId: string, title = '') => {
    const now = Date.now();
    const session: AgentSession = {
      id: newSessionId(),
      title,
      modelId,
      messages: [],
      createdAt: now,
      updatedAt: now,
    };
    setStore((prev) => ({
      activeSessionId: session.id,
      sessions: sortSessions([session, ...prev.sessions]).slice(0, MAX_SESSIONS),
    }));
    return session.id;
  }, []);

  const selectSession = useCallback((sessionId: string) => {
    setStore((prev) => {
      if (!prev.sessions.some((session) => session.id === sessionId)) {
        return prev;
      }
      return { ...prev, activeSessionId: sessionId };
    });
  }, []);

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
          };
        });
        return { ...prev, sessions: sortSessions(sessions) };
      });
    },
    [],
  );

  const deleteSession = useCallback((sessionId: string) => {
    setStore((prev) => {
      const sessions = prev.sessions.filter((session) => session.id !== sessionId);
      const activeSessionId =
        prev.activeSessionId === sessionId ? (sessions[0]?.id ?? null) : prev.activeSessionId;
      return { activeSessionId, sessions };
    });
  }, []);

  return {
    sessions: store.sessions,
    activeSessionId: store.activeSessionId,
    activeSession,
    createSession,
    selectSession,
    ensureActiveSession,
    replaceSessionMessages,
    deleteSession,
  };
}
