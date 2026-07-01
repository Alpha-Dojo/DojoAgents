import type {
  AgentActivityStep,
  AgentChatMessage,
  AgentSession,
  AgentSessionStore,
} from '../types/agent';

export const MAX_AGENT_SESSIONS = 50;
export const MAX_AGENT_SESSION_STORAGE_BYTES = 3_500_000;

const FALLBACK_BYTE_BUDGETS = [
  MAX_AGENT_SESSION_STORAGE_BYTES,
  2_000_000,
  1_000_000,
  500_000,
  125_000,
];
const MIN_RETAINED_MESSAGES = 2;
const MAX_FALLBACK_CONTENT_CHARS = 16_000;

interface StorageWriter {
  setItem(key: string, value: string): void;
}

interface BoundStoreOptions {
  maxBytes?: number;
  maxSessions?: number;
}

interface WriteStoreOptions {
  byteBudgets?: number[];
  maxSessions?: number;
}

export interface SessionStoreWriteResult {
  ok: boolean;
  store: AgentSessionStore;
}

function compactActivityStep(step: AgentActivityStep): AgentActivityStep {
  if (step.kind !== 'tool' || step.item.status !== 'done' || step.item.data == null) {
    return step;
  }
  const { data: _data, ...item } = step.item;
  return { ...step, item };
}

/**
 * Produce the UI-complete, storage-safe form of messages.
 *
 * Successful raw tool data is omitted because persisted result summaries and visualization blocks
 * already contain the representation used by the history UI. Live run state is never mutated.
 */
export function compactMessagesForStorage(
  messages: AgentChatMessage[],
): AgentChatMessage[] {
  return messages.map((message) => {
    const activitySteps = message.activitySteps?.map(compactActivityStep);
    const toolActivity = message.toolActivity?.map((item) => {
      if (item.status !== 'done' || item.data == null) return item;
      const { data: _data, ...compacted } = item;
      return compacted;
    });
    const { images: _images, ...rest } = message;
    return {
      ...rest,
      ...(activitySteps ? { activitySteps } : {}),
      ...(toolActivity ? { toolActivity } : {}),
    };
  });
}

function compactSession(session: AgentSession): AgentSession {
  return {
    ...session,
    messages: compactMessagesForStorage(session.messages),
  };
}

function estimateBytes(store: AgentSessionStore): number {
  return JSON.stringify(store).length * 2;
}

function sortSessions(sessions: AgentSession[]): AgentSession[] {
  return [...sessions].sort((left, right) => right.updatedAt - left.updatedAt);
}

function limitSessionCount(
  sessions: AgentSession[],
  activeSessionId: string | null,
  maxSessions: number,
): AgentSession[] {
  if (sessions.length <= maxSessions) return sessions;
  const limited = sessions.slice(0, maxSessions);
  if (!activeSessionId || limited.some((session) => session.id === activeSessionId)) {
    return limited;
  }
  const active = sessions.find((session) => session.id === activeSessionId);
  if (!active || maxSessions === 0) return limited;
  return sortSessions([...limited.slice(0, -1), active]);
}

function trimOldestInactiveSession(store: AgentSessionStore): AgentSessionStore | null {
  const removable = [...store.sessions]
    .filter((session) => session.id !== store.activeSessionId)
    .sort((left, right) => left.updatedAt - right.updatedAt)[0];
  if (!removable) return null;
  return {
    ...store,
    sessions: store.sessions.filter((session) => session.id !== removable.id),
  };
}

function trimOldestMessage(store: AgentSessionStore): AgentSessionStore | null {
  const active = store.sessions.find((session) => session.id === store.activeSessionId);
  const target =
    active ??
    [...store.sessions].sort((left, right) => right.messages.length - left.messages.length)[0];
  if (!target || target.messages.length <= MIN_RETAINED_MESSAGES) return null;
  return {
    ...store,
    sessions: store.sessions.map((session) =>
      session.id === target.id
        ? { ...session, messages: session.messages.slice(1) }
        : session,
    ),
  };
}

function createMinimalStore(store: AgentSessionStore): AgentSessionStore {
  const active =
    store.sessions.find((session) => session.id === store.activeSessionId) ??
    store.sessions[0];
  if (!active) return { activeSessionId: null, sessions: [] };
  const messages = active.messages.slice(-MIN_RETAINED_MESSAGES).map((message) => ({
    role: message.role,
    content: message.content.slice(-MAX_FALLBACK_CONTENT_CHARS),
  }));
  return {
    activeSessionId: active.id,
    sessions: [{ ...active, messages }],
  };
}

export function boundSessionStore(
  store: AgentSessionStore,
  options: BoundStoreOptions = {},
): AgentSessionStore {
  const maxBytes = Math.max(0, options.maxBytes ?? MAX_AGENT_SESSION_STORAGE_BYTES);
  const maxSessions = Math.max(0, options.maxSessions ?? MAX_AGENT_SESSIONS);
  let bounded: AgentSessionStore = {
    activeSessionId: store.activeSessionId,
    sessions: limitSessionCount(
      sortSessions(store.sessions.map(compactSession)),
      store.activeSessionId,
      maxSessions,
    ),
  };

  while (estimateBytes(bounded) > maxBytes) {
    const withoutOldest = trimOldestInactiveSession(bounded);
    if (withoutOldest) {
      bounded = withoutOldest;
      continue;
    }
    const withoutOldestMessage = trimOldestMessage(bounded);
    if (withoutOldestMessage) {
      bounded = withoutOldestMessage;
      continue;
    }
    bounded = createMinimalStore(bounded);
    break;
  }
  return bounded;
}

export function trySetStorage(
  storage: StorageWriter,
  key: string,
  value: string,
): boolean {
  try {
    storage.setItem(key, value);
    return true;
  } catch {
    return false;
  }
}

export function writeSessionStore(
  storage: StorageWriter,
  key: string,
  store: AgentSessionStore,
  options: WriteStoreOptions = {},
): SessionStoreWriteResult {
  const budgets = options.byteBudgets ?? FALLBACK_BYTE_BUDGETS;
  let candidate = boundSessionStore(store, {
    maxBytes: budgets[0] ?? MAX_AGENT_SESSION_STORAGE_BYTES,
    maxSessions: options.maxSessions,
  });
  for (const maxBytes of budgets) {
    candidate = boundSessionStore(store, {
      maxBytes,
      maxSessions: options.maxSessions,
    });
    if (trySetStorage(storage, key, JSON.stringify(candidate))) {
      return { ok: true, store: candidate };
    }
  }
  return { ok: false, store: candidate };
}
