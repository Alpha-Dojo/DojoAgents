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
export type AgentPhase = 'planning' | 'tools' | 'answering';

export interface AgentResourceChange {
  resource: string;
  action: string;
  portfolio_id?: string;
}

export interface AgentVizBlock {
  kind?: string;
  title?: string;
  data?: unknown;
  [key: string]: unknown;
}

export interface AgentToolActivityItem {
  id: string;
  tool: string;
  arguments?: string;
  status: AgentToolActivityStatus;
  error?: string | null;
  result?: string;
  latencyMs?: number;
  data?: unknown;
  vizBlocks?: AgentVizBlock[];
  resourceChanges?: AgentResourceChange[];
}

export interface AgentChatMessage {
  role: AgentChatRole;
  content: string;
  toolActivity?: AgentToolActivityItem[];
  phase?: AgentPhase;
  phaseHistory?: AgentPhase[];
  retries?: string[];
  evalHints?: string[];
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

export interface ChatMessage {
  role: 'system' | 'user' | 'assistant' | 'tool';
  content: string | null;
  tool_calls?: ToolCall[];
  tool_call_id?: string;
}

export interface ToolCall {
  id: string;
  type: 'function';
  function: { name: string; arguments: string };
}

export interface ToolDefinition {
  type: 'function';
  function: {
    name: string;
    description?: string;
    parameters?: Record<string, unknown>;
  };
}

export interface AgentChatRequest {
  model: string;
  messages: ChatMessage[];
  stream?: boolean;
  tools?: ToolDefinition[];
  tool_choice?: 'auto' | 'none' | 'required' | object;
  temperature?: number;
  user?: string;
  metadata?: Record<string, unknown>;
}

export interface AgentChatResponse {
  id: string;
  object: 'chat.completion';
  created: number;
  model: string;
  choices: CompletionChoice[];
  usage: UsageInfo;
  content?: string;
  session_id?: string;
  dojo?: {
    schema_version: string;
    run_id: string;
    events: DojoEvent[];
  };
}

export interface CompletionChoice {
  index: number;
  message: ChatMessage;
  finish_reason: 'stop' | 'tool_calls' | null;
}

export interface ChatCompletionChunk {
  id: string;
  object: 'chat.completion.chunk';
  created: number;
  model: string;
  choices: ChunkChoice[];
  dojo_event?: DojoEvent;
}

export interface ChunkChoice {
  index: number;
  delta: {
    role?: string;
    content?: string;
    tool_calls?: ToolCall[];
  };
  finish_reason: 'stop' | 'tool_calls' | null;
}

export interface UsageInfo {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

export interface DojoEventBase {
  schema_version: string;
  run_id: string;
  seq: number;
  type:
    | 'delta'
    | 'phase'
    | 'think_start'
    | 'think_delta'
    | 'think_end'
    | 'retry'
    | 'tool_start'
    | 'tool_result'
    | 'eval_hint'
    | 'done'
    | 'error';
  session_id: string;
  timestamp: string;
}

export interface DojoDeltaEvent extends DojoEventBase {
  type: 'delta';
  text: string;
}

export interface DojoPhaseEvent extends DojoEventBase {
  type: 'phase';
  phase: AgentPhase;
}

export interface DojoRetryEvent extends DojoEventBase {
  type: 'retry';
  attempt: number;
  max_attempts: number;
  text: string;
}

export interface DojoToolStartEvent extends DojoEventBase {
  type: 'tool_start';
  call_id: string;
  tool: string;
  arguments: Record<string, unknown>;
}

export interface DojoToolResultEvent extends DojoEventBase {
  type: 'tool_result';
  call_id: string;
  tool: string;
  ok: boolean;
  content: string;
  error: string;
  latency_ms: number;
  truncated: boolean;
  data: unknown;
  viz_blocks: AgentVizBlock[];
  artifacts: Record<string, unknown>[];
  resource_changes: AgentResourceChange[];
}

export interface DojoEvalHintEvent extends DojoEventBase {
  type: 'eval_hint';
  text: string;
  issues: string[];
}

export interface DojoDoneEvent extends DojoEventBase {
  type: 'done';
  model_id: string;
  tool_trace: Array<Record<string, unknown>>;
  tool_steps: number;
}

export interface DojoErrorEvent extends DojoEventBase {
  type: 'error';
  message: string;
  code?: string;
}

export type DojoEvent =
  | DojoDeltaEvent
  | DojoPhaseEvent
  | DojoRetryEvent
  | DojoToolStartEvent
  | DojoToolResultEvent
  | DojoEvalHintEvent
  | DojoDoneEvent
  | DojoErrorEvent
  | DojoEventBase;

export type AgentStreamEventType =
  | 'content_delta'
  | 'tool_call_delta'
  | 'dojo_event'
  | 'message_end'
  | 'done'
  | 'error';

export interface AgentStreamEvent {
  type: AgentStreamEventType;
  chunk?: ChatCompletionChunk;
  content?: string;
  dojoEvent?: DojoEvent;
  error?: Error;
}
