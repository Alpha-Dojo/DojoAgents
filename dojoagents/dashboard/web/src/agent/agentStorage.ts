import type { AgentChatMessage } from '../types/agent';

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

export function saveActiveRunDraft(draft: AgentActiveRunDraft): void {
  localStorage.setItem(AGENT_ACTIVE_RUN_STORAGE_KEY, JSON.stringify(draft));
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

export function saveStreamDraft(draft: AgentStreamDraft): void {
  localStorage.setItem(AGENT_DRAFT_STORAGE_KEY, JSON.stringify(draft));
}

export function clearStreamDraft(): void {
  localStorage.removeItem(AGENT_DRAFT_STORAGE_KEY);
}
