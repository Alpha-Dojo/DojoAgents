export interface AgentModelItem {
  id: string;
  label: string;
  provider: string;
  model: string;
  available: boolean;
  unavailable_reason?: string | null;
}

export interface AgentModelsResponse {
  default_model_id: string;
  gemini_configured: boolean;
  zhipu_configured: boolean;
  agent_ready: boolean;
  models: AgentModelItem[];
}

export type AgentChatRole = 'user' | 'assistant';

export type AgentToolActivityStatus = 'running' | 'done' | 'error';

export interface AgentToolActivityItem {
  callId?: string;
  tool: string;
  status: AgentToolActivityStatus;
  latencyMs?: number;
  error?: string | null;
  arguments?: Record<string, unknown>;
  data?: Record<string, unknown> | null;
  resultSummary?: string | null;
  vizBlocks?: import('./agentViz').AgentVizBlock[];
}

export interface AgentEvalHintItem {
  id: string;
  issues: string[];
}

export interface AgentThinkBlock {
  id: string;
  text: string;
  collapsed: boolean;
  done: boolean;
}

export type AgentActivityStep =
  | { kind: 'think'; id: string; block: AgentThinkBlock }
  | { kind: 'tool'; id: string; item: AgentToolActivityItem }
  | { kind: 'eval'; id: string; hint: AgentEvalHintItem };

export interface AgentChatMessage {
  role: AgentChatRole;
  content: string;
  /** Chronological stream of thinking, tools, and eval hints. */
  activitySteps?: AgentActivityStep[];
  /** @deprecated Migrated into activitySteps for display order. */
  toolActivity?: AgentToolActivityItem[];
  /** @deprecated Migrated into activitySteps for display order. */
  thinkBlocks?: AgentThinkBlock[];
  /** @deprecated Migrated into activitySteps for display order. */
  evalHints?: AgentEvalHintItem[];
}

export type AgentLocale = 'zh' | 'en';

export interface AgentChatRequest {
  model_id: string;
  messages: AgentChatMessage[];
  locale?: AgentLocale;
  use_tools?: boolean;
  max_tool_steps?: number;
  exclude_mutating_tools?: boolean;
}

export interface AgentToolTraceItem {
  call_id?: string;
  tool: string;
  arguments: Record<string, unknown>;
  ok: boolean;
  latency_ms: number;
  truncated: boolean;
  error?: string | null;
  data?: Record<string, unknown> | null;
  viz_blocks?: import('./agentViz').AgentVizBlock[];
  artifacts?: Record<string, unknown>[];
  resource_changes?: Record<string, unknown>[];
}

export interface AgentChatResponse {
  model_id: string;
  message: AgentChatMessage;
  tool_trace?: AgentToolTraceItem[];
  tool_steps?: number;
}

export interface AgentSession {
  id: string;
  title: string;
  modelId: string;
  messages: AgentChatMessage[];
  createdAt: number;
  updatedAt: number;
}

export interface AgentSessionStore {
  activeSessionId: string | null;
  sessions: AgentSession[];
}

export type AgentStreamEvent =
  | { type: 'delta'; text: string }
  | { type: 'think_start' }
  | { type: 'think_delta'; text: string }
  | { type: 'think_end' }
  | { type: 'phase'; phase: 'planning' | 'tools' | 'answering' }
  | { type: 'retry'; attempt: number; max_attempts: number; text: string }
  | { type: 'tool_start'; call_id?: string; tool: string; arguments: Record<string, unknown> }
  | {
      type: 'tool_result';
      call_id?: string;
      tool: string;
      ok: boolean;
      latency_ms: number;
      truncated: boolean;
      error?: string | null;
      data?: Record<string, unknown> | null;
      viz_blocks?: import('./agentViz').AgentVizBlock[];
    }
  | { type: 'eval_hint'; text: string; issues: string[] }
  | { type: 'done'; model_id: string; tool_trace?: AgentToolTraceItem[]; tool_steps?: number }
  | { type: 'error'; message: string };
