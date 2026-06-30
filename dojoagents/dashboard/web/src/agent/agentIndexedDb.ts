import type { AgentStreamDraft } from './agentStorage';
import type { AgentSession, AgentSessionStore } from '../types/agent';
import { chooseHydratedStore } from './agentIndexedDbPolicy';

const DATABASE_NAME = 'dojo-agent-db';
const DATABASE_VERSION = 1;
const SESSION_STORE = 'sessions';
const DRAFT_STORE = 'drafts';
const METADATA_STORE = 'metadata';
const ACTIVE_SESSION_KEY = 'activeSessionId';
const DRAFT_WRITE_DELAY_MS = 120;
const DATABASE_RETRY_DELAY_MS = 1_000;

export type AgentStorageStatus =
  | 'initializing'
  | 'ready'
  | 'fallback'
  | 'blocked'
  | 'quota'
  | 'failed';

interface MetadataRecord {
  key: string;
  value: unknown;
}

let databasePromise: Promise<IDBDatabase | null> | null = null;
let databaseRetryAfter = 0;
let writeQueue: Promise<void> = Promise.resolve();
const syncedSessionVersions = new Map<string, string>();
const pendingDrafts = new Map<string, AgentStreamDraft>();
let draftFlushTimer: ReturnType<typeof setTimeout> | null = null;
let storageStatus: AgentStorageStatus = 'initializing';
const storageStatusListeners = new Set<() => void>();

function setStorageStatus(nextStatus: AgentStorageStatus): void {
  if (storageStatus === nextStatus) return;
  storageStatus = nextStatus;
  for (const listener of storageStatusListeners) listener();
}

export function getAgentStorageStatus(): AgentStorageStatus {
  return storageStatus;
}

export function subscribeAgentStorageStatus(listener: () => void): () => void {
  storageStatusListeners.add(listener);
  return () => storageStatusListeners.delete(listener);
}

function reportStorageError(error: unknown): void {
  if (error instanceof DOMException && error.name === 'QuotaExceededError') {
    setStorageStatus('quota');
    return;
  }
  setStorageStatus('failed');
}

function sessionVersion(session: AgentSession): string {
  return session.revision === undefined
    ? `t:${session.updatedAt}`
    : `r:${session.revision}`;
}

function requestResult<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error('IndexedDB request failed'));
  });
}

function transactionDone(transaction: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => {
      setStorageStatus('ready');
      resolve();
    };
    transaction.onabort = () =>
      reject(transaction.error ?? new Error('IndexedDB transaction aborted'));
    transaction.onerror = () =>
      reject(transaction.error ?? new Error('IndexedDB transaction failed'));
  });
}

function openDatabase(): Promise<IDBDatabase | null> {
  if (databasePromise) return databasePromise;
  if (Date.now() < databaseRetryAfter) return Promise.resolve(null);
  databasePromise = new Promise((resolve) => {
    if (typeof indexedDB === 'undefined') {
      setStorageStatus('fallback');
      databasePromise = null;
      resolve(null);
      return;
    }
    let settled = false;
    const request = indexedDB.open(DATABASE_NAME, DATABASE_VERSION);
    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(SESSION_STORE)) {
        const sessions = database.createObjectStore(SESSION_STORE, { keyPath: 'id' });
        sessions.createIndex('updatedAt', 'updatedAt');
      }
      if (!database.objectStoreNames.contains(DRAFT_STORE)) {
        const drafts = database.createObjectStore(DRAFT_STORE, { keyPath: 'sessionId' });
        drafts.createIndex('updatedAt', 'updatedAt');
      }
      if (!database.objectStoreNames.contains(METADATA_STORE)) {
        database.createObjectStore(METADATA_STORE, { keyPath: 'key' });
      }
    };
    request.onsuccess = () => {
      if (settled) {
        request.result.close();
        return;
      }
      settled = true;
      const database = request.result;
      database.onversionchange = () => database.close();
      setStorageStatus('ready');
      resolve(database);
    };
    request.onerror = () => {
      if (settled) return;
      settled = true;
      databasePromise = null;
      databaseRetryAfter = Date.now() + DATABASE_RETRY_DELAY_MS;
      reportStorageError(request.error);
      resolve(null);
    };
    request.onblocked = () => {
      if (settled) return;
      settled = true;
      databasePromise = null;
      databaseRetryAfter = Date.now() + DATABASE_RETRY_DELAY_MS;
      setStorageStatus('blocked');
      resolve(null);
    };
  });
  return databasePromise;
}

function enqueueWrite(operation: () => Promise<void>): Promise<void> {
  const queued = writeQueue.then(operation, operation);
  writeQueue = queued.catch(() => {});
  return queued;
}

async function readSessionStore(database: IDBDatabase): Promise<AgentSessionStore> {
  const transaction = database.transaction(
    [SESSION_STORE, METADATA_STORE],
    'readonly',
  );
  const sessionsRequest = transaction.objectStore(SESSION_STORE).getAll() as IDBRequest<
    AgentSession[]
  >;
  const activeRequest = transaction
    .objectStore(METADATA_STORE)
    .get(ACTIVE_SESSION_KEY) as IDBRequest<MetadataRecord | undefined>;
  const [sessions, activeRecord] = await Promise.all([
    requestResult(sessionsRequest),
    requestResult(activeRequest),
    transactionDone(transaction),
  ]);
  for (const session of sessions) {
    syncedSessionVersions.set(session.id, sessionVersion(session));
  }
  return {
    activeSessionId:
      typeof activeRecord?.value === 'string' ? activeRecord.value : null,
    sessions: [...sessions].sort((left, right) => right.updatedAt - left.updatedAt),
  };
}

async function writeFullStore(
  database: IDBDatabase,
  store: AgentSessionStore,
): Promise<void> {
  const transaction = database.transaction(
    [SESSION_STORE, METADATA_STORE],
    'readwrite',
  );
  const sessionStore = transaction.objectStore(SESSION_STORE);
  const currentIds = new Set(store.sessions.map((session) => session.id));
  const deletedIds: string[] = [];
  const writtenSessions: AgentSession[] = [];
  const storedKeys = await requestResult(sessionStore.getAllKeys());
  for (const key of storedKeys) {
    const id = String(key);
    if (!currentIds.has(id)) {
      sessionStore.delete(key);
      deletedIds.push(id);
    }
  }
  for (const session of store.sessions) {
    if (syncedSessionVersions.get(session.id) !== sessionVersion(session)) {
      sessionStore.put(session);
      writtenSessions.push(session);
    }
  }
  transaction.objectStore(METADATA_STORE).put({
    key: ACTIVE_SESSION_KEY,
    value: store.activeSessionId,
  } satisfies MetadataRecord);
  await transactionDone(transaction);
  for (const id of deletedIds) syncedSessionVersions.delete(id);
  for (const session of writtenSessions) {
    syncedSessionVersions.set(session.id, sessionVersion(session));
  }
}

export async function hydrateAgentSessionStore(
  localFallback: AgentSessionStore,
): Promise<AgentSessionStore> {
  try {
    await writeQueue;
    const database = await openDatabase();
    if (!database) return localFallback;
    const indexedStore = await readSessionStore(database);
    if (indexedStore.sessions.length === 0 && localFallback.sessions.length > 0) {
      await enqueueWrite(() => writeFullStore(database, localFallback));
    }
    return chooseHydratedStore(localFallback, indexedStore);
  } catch (error) {
    reportStorageError(error);
    return localFallback;
  }
}

export function syncAgentSessionStore(store: AgentSessionStore): Promise<void> {
  return enqueueWrite(async () => {
    try {
      const database = await openDatabase();
      if (!database) return;
      await writeFullStore(database, store);
    } catch (error) {
      reportStorageError(error);
      // localStorage remains the synchronous fallback
    }
  });
}

export function putAgentSession(session: AgentSession): Promise<void> {
  return enqueueWrite(async () => {
    try {
      const database = await openDatabase();
      if (!database) return;
      const transaction = database.transaction(SESSION_STORE, 'readwrite');
      transaction.objectStore(SESSION_STORE).put(session);
      await transactionDone(transaction);
      syncedSessionVersions.set(session.id, sessionVersion(session));
    } catch (error) {
      reportStorageError(error);
      // localStorage remains the synchronous fallback
    }
  });
}

export function updateAgentSessionMessages(
  sessionId: string,
  messages: AgentSession['messages'],
  modelId: string | undefined,
  updatedAt: number,
  revision: number,
): Promise<void> {
  return enqueueWrite(async () => {
    try {
      const database = await openDatabase();
      if (!database) return;
      const transaction = database.transaction(SESSION_STORE, 'readwrite');
      const store = transaction.objectStore(SESSION_STORE);
      const existing = await requestResult(
        store.get(sessionId) as IDBRequest<AgentSession | undefined>,
      );
      if (existing) {
        store.put({
          ...existing,
          messages,
          modelId: modelId ?? existing.modelId,
          updatedAt,
          revision,
        });
      }
      await transactionDone(transaction);
      if (existing) syncedSessionVersions.set(sessionId, `r:${revision}`);
    } catch (error) {
      reportStorageError(error);
      // localStorage remains the synchronous fallback
    }
  });
}

async function writeDraftBatch(drafts: AgentStreamDraft[]): Promise<void> {
  try {
    const database = await openDatabase();
    if (!database) return;
    const transaction = database.transaction(DRAFT_STORE, 'readwrite');
    const store = transaction.objectStore(DRAFT_STORE);
    for (const draft of drafts) store.put(draft);
    await transactionDone(transaction);
  } catch (error) {
    reportStorageError(error);
    // compact local draft remains available
  }
}

function flushPendingDrafts(): void {
  draftFlushTimer = null;
  if (pendingDrafts.size === 0) return;
  const drafts = [...pendingDrafts.values()];
  pendingDrafts.clear();
  void enqueueWrite(() => writeDraftBatch(drafts));
}

export function putAgentStreamDraft(draft: AgentStreamDraft): void {
  pendingDrafts.set(draft.sessionId, draft);
  if (draftFlushTimer !== null) return;
  draftFlushTimer = setTimeout(flushPendingDrafts, DRAFT_WRITE_DELAY_MS);
}

export async function getAgentStreamDraft(
  sessionId?: string,
): Promise<AgentStreamDraft | null> {
  try {
    const database = await openDatabase();
    if (!database) return null;
    const transaction = database.transaction(DRAFT_STORE, 'readonly');
    const store = transaction.objectStore(DRAFT_STORE);
    if (sessionId) {
      const draft = await requestResult(
        store.get(sessionId) as IDBRequest<AgentStreamDraft | undefined>,
      );
      await transactionDone(transaction);
      return draft ?? null;
    }
    const drafts = await requestResult(store.getAll() as IDBRequest<AgentStreamDraft[]>);
    await transactionDone(transaction);
    return (
      [...drafts].sort((left, right) => right.updatedAt - left.updatedAt)[0] ?? null
    );
  } catch (error) {
    reportStorageError(error);
    return null;
  }
}

export function clearAgentStreamDrafts(): Promise<void> {
  if (draftFlushTimer !== null) {
    clearTimeout(draftFlushTimer);
    draftFlushTimer = null;
  }
  pendingDrafts.clear();
  return enqueueWrite(async () => {
    try {
      const database = await openDatabase();
      if (!database) return;
      const transaction = database.transaction(DRAFT_STORE, 'readwrite');
      transaction.objectStore(DRAFT_STORE).clear();
      await transactionDone(transaction);
    } catch (error) {
      reportStorageError(error);
      // compact local draft has already been cleared
    }
  });
}
