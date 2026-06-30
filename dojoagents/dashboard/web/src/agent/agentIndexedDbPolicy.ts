import type { AgentSession, AgentSessionStore } from '../types/agent';
import type { AgentStreamDraft } from './agentStorage';

export interface AgentSessionSummary {
  id: string;
  title: string;
  modelId: string;
  createdAt: number;
  updatedAt: number;
}

export interface AgentSessionSummaryStore {
  activeSessionId: string | null;
  sessions: AgentSessionSummary[];
}

export function chooseHydratedStore(
  localStore: AgentSessionStore,
  indexedDbStore: AgentSessionStore | null,
): AgentSessionStore {
  if (!indexedDbStore || indexedDbStore.sessions.length === 0) {
    return localStore;
  }
  return mergeSessionStores(localStore, indexedDbStore);
}

export function mergeSessionStores(
  currentStore: AgentSessionStore,
  hydratedStore: AgentSessionStore,
): AgentSessionStore {
  const byId = new Map<string, AgentSession>();
  for (const session of currentStore.sessions) {
    byId.set(session.id, session);
  }
  for (const session of hydratedStore.sessions) {
    const current = byId.get(session.id);
    if (!current || compareSessionFreshness(session, current) >= 0) {
      byId.set(session.id, session);
    }
  }
  return {
    activeSessionId:
      currentStore.activeSessionId ??
      hydratedStore.activeSessionId,
    sessions: [...byId.values()].sort((left, right) => right.updatedAt - left.updatedAt),
  };
}

export function compareSessionFreshness(
  left: AgentSession,
  right: AgentSession,
): number {
  if (
    left.revision !== undefined &&
    right.revision !== undefined &&
    left.revision !== right.revision
  ) {
    return left.revision - right.revision;
  }
  return left.updatedAt - right.updatedAt;
}

export function sessionSummariesFromStore(
  store: AgentSessionStore,
): AgentSessionSummaryStore {
  return {
    activeSessionId: store.activeSessionId,
    sessions: store.sessions.map(({ id, title, modelId, createdAt, updatedAt }) => ({
      id,
      title,
      modelId,
      createdAt,
      updatedAt,
    })),
  };
}

export function chooseStreamDraft(
  localDraft: AgentStreamDraft | null,
  archivedDraft: AgentStreamDraft | null,
): AgentStreamDraft | null {
  if (!localDraft) return archivedDraft;
  if (!archivedDraft || archivedDraft.sessionId !== localDraft.sessionId) {
    return localDraft;
  }
  if (archivedDraft.updatedAt !== localDraft.updatedAt) {
    return archivedDraft.updatedAt > localDraft.updatedAt ? archivedDraft : localDraft;
  }
  const localCursor = localDraft.eventCursor ?? -1;
  const archivedCursor = archivedDraft.eventCursor ?? -1;
  return archivedCursor > localCursor ? archivedDraft : localDraft;
}

export function withFallbackTimeout<T>(
  operation: Promise<T>,
  fallback: T,
  timeoutMs: number,
): Promise<T> {
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve(fallback), timeoutMs);
    operation.then(
      (value) => {
        clearTimeout(timer);
        resolve(value);
      },
      () => {
        clearTimeout(timer);
        resolve(fallback);
      },
    );
  });
}
