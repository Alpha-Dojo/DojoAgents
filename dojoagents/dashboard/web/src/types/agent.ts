export interface AgentModelItem {
  id: string;
  label: string;
  provider: string;
  available: boolean;
}

export interface AgentModelsResponse {
  default_model_id: string;
  gemini_configured: boolean;
  models: AgentModelItem[];
}

export type AgentChatRole = 'user' | 'assistant';

export type AgentToolActivityStatus = 'running' | 'done' | 'error';

export interface AgentToolActivityItem {
  tool: string;
  status: AgentToolActivityStatus;
  latencyMs?: number;
  error?: string | null;
  arguments?: Record<string, unknown>;
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

export interface AgentChatMessage {
  role: AgentChatRole;
  content: string;
  toolActivity?: AgentToolActivityItem[];
  thinkBlocks?: AgentThinkBlock[];
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
  tool: string;
  arguments: Record<string, unknown>;
  ok: boolean;
  latency_ms: number;
  truncated: boolean;
  error?: string | null;
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
  | { type: 'tool_start'; tool: string; arguments: Record<string, unknown> }
  | {
      type: 'tool_result';
      tool: string;
      ok: boolean;
      latency_ms: number;
      truncated: boolean;
      error?: string | null;
      data?: {
        portfolio_id?: string;
        name?: string;
        holdings_count?: number;
        holdings_by_market?: Record<string, number>;
        tickers?: string[];
      } | null;
      viz_blocks?: import('./agentViz').AgentVizBlock[];
    }
  | { type: 'eval_hint'; text: string; issues: string[] }
  | { type: 'done'; model_id: string; tool_trace?: AgentToolTraceItem[]; tool_steps?: number }
  | { type: 'error'; message: string };
