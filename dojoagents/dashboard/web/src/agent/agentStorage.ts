import type { AgentChatMessage } from '../types/agent';
import { compactMessagesForStorage, trySetStorage } from './agentStoragePolicy';
import {
  clearAgentStreamDrafts,
  getAgentStreamDraft,
  putAgentStreamDraft,
} from './agentIndexedDb';
import { chooseStreamDraft } from './agentIndexedDbPolicy';

/** 历史会话列表与当前选中会话 */
export const AGENT_SESSIONS_STORAGE_KEY = 'dojo-agent-sessions-v1';

/** 进行中的对话草稿（刷新恢复用） */
export const AGENT_DRAFT_STORAGE_KEY = 'dojo-agent-draft-v1';

export interface AgentStreamDraft {
  sessionId: string;
  modelId: string;
  messages: AgentChatMessage[];
  updatedAt: number;
  interrupted: boolean;
  /** Number of server events already reflected in `messages`. */
  eventCursor?: number;
}

/** Active background run — survives UI navigation. */
export const AGENT_ACTIVE_RUN_STORAGE_KEY = 'dojo-agent-active-run-v1';

export interface AgentActiveRunDraft {
  sessionId: string;
  runId: string;
  modelId: string;
  cursor: number;
  updatedAt: number;
}

export function loadActiveRunDraft(): AgentActiveRunDraft | null {
  try {
    const raw = localStorage.getItem(AGENT_ACTIVE_RUN_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as AgentActiveRunDraft;
    if (!parsed?.sessionId || !parsed?.runId) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function saveActiveRunDraft(draft: AgentActiveRunDraft): boolean {
  return trySetStorage(
    localStorage,
    AGENT_ACTIVE_RUN_STORAGE_KEY,
    JSON.stringify(draft),
  );
}

export function clearActiveRunDraft(): void {
  localStorage.removeItem(AGENT_ACTIVE_RUN_STORAGE_KEY);
}

export function loadStreamDraft(): AgentStreamDraft | null {
  try {
    const raw = localStorage.getItem(AGENT_DRAFT_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as AgentStreamDraft;
    if (!parsed?.sessionId || !Array.isArray(parsed.messages)) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function saveStreamDraft(draft: AgentStreamDraft): boolean {
  void putAgentStreamDraft(draft);
  return trySetStorage(
    localStorage,
    AGENT_DRAFT_STORAGE_KEY,
    JSON.stringify({
      ...draft,
      messages: compactMessagesForStorage(draft.messages),
    }),
  );
}

export function clearStreamDraft(): void {
  localStorage.removeItem(AGENT_DRAFT_STORAGE_KEY);
  void clearAgentStreamDrafts();
}

export async function loadStreamDraftFull(
  sessionId?: string,
): Promise<AgentStreamDraft | null> {
  const fallback = loadStreamDraft();
  const targetSessionId = sessionId ?? fallback?.sessionId;
  if (!targetSessionId) return fallback;
  const archived = await getAgentStreamDraft(targetSessionId);
  return chooseStreamDraft(fallback, archived);
}
