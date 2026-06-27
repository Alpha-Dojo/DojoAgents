import { AGENT_SESSIONS_STORAGE_KEY } from './agentStorage';
import type { AgentChatMessage, AgentSession, AgentSessionStore } from '../types/agent';
import { deriveSessionTitle } from './useAgentSessions';
import { writeSessionStore } from './agentStoragePolicy';
import { updateAgentSessionMessages } from './agentIndexedDb';

function loadStore(): AgentSessionStore {
  try {
    const raw = localStorage.getItem(AGENT_SESSIONS_STORAGE_KEY);
    if (!raw) return { activeSessionId: null, sessions: [] };
    const parsed = JSON.parse(raw) as AgentSessionStore;
    if (!Array.isArray(parsed.sessions)) return { activeSessionId: null, sessions: [] };
    return {
      activeSessionId: parsed.activeSessionId ?? null,
      sessions: parsed.sessions.filter((session) => session && session.id),
    };
  } catch {
    return { activeSessionId: null, sessions: [] };
  }
}

function sortSessions(sessions: AgentSession[]): AgentSession[] {
  return [...sessions].sort((a, b) => b.updatedAt - a.updatedAt);
}

/** Persist session messages without React state — used when run finishes off-panel. */
export function persistSessionMessagesSync(
  sessionId: string,
  messages: AgentChatMessage[],
  modelId?: string,
): void {
  const store = loadStore();
  const now = Date.now();
  const firstUser = messages.find((message) => message.role === 'user');
  const sessions = store.sessions.map((session) => {
    if (session.id !== sessionId) return session;
    const revision = (session.revision ?? 0) + 1;
    void updateAgentSessionMessages(sessionId, messages, modelId, now, revision);
    return {
      ...session,
      messages,
      modelId: modelId ?? session.modelId,
      title:
        !session.title.trim() && firstUser
          ? deriveSessionTitle(firstUser.content)
          : session.title,
      updatedAt: now,
      revision,
    };
  });
  if (!sessions.some((session) => session.id === sessionId)) return;
  writeSessionStore(
    localStorage,
    AGENT_SESSIONS_STORAGE_KEY,
    { ...store, sessions: sortSessions(sessions) },
  );
}
