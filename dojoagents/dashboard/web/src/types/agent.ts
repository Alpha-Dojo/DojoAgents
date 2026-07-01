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

export type AgentApiContentPart =
  | { type: 'text'; text: string }
  | { type: 'image_url'; image_url: { url: string } };

export type AgentApiMessage = {
  role: AgentChatRole;
  content: string | AgentApiContentPart[];
};

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
  resultContent?: string | null;
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

export interface AgentChatImageAttachment {
  dataUrl: string;
  name?: string;
}

export interface AgentChatMessage {
  role: AgentChatRole;
  content: string;
  /** Pasted or uploaded images attached to a user message. */
  images?: AgentChatImageAttachment[];
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
  session_id: string;
  model_id: string;
  messages: AgentApiMessage[];
  locale?: AgentLocale;
  dashboard_tab?: string;
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
  /** Monotonic local version used to resolve async persistence races. */
  revision?: number;
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
      content?: string;
      latency_ms: number;
      truncated: boolean;
      error?: string | null;
      data?: Record<string, unknown> | null;
      viz_blocks?: import('./agentViz').AgentVizBlock[];
      resource_changes?: Record<string, unknown>[];
    }
  | { type: 'eval_hint'; text: string; issues: string[] }
  | { type: 'done'; model_id: string; tool_trace?: AgentToolTraceItem[]; tool_steps?: number }
  | { type: 'error'; message: string };
