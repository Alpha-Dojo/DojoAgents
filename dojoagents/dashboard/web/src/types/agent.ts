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
  id: string;
  tool: string;
  arguments?: string;
  status: AgentToolActivityStatus;
  error?: string | null;
}

export interface AgentChatMessage {
  role: AgentChatRole;
  content: string;
  toolActivity?: AgentToolActivityItem[];
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

export type AgentStreamEventType = 'content_delta' | 'tool_call_delta' | 'message_end' | 'done' | 'error';

export interface AgentStreamEvent {
  type: AgentStreamEventType;
  chunk?: ChatCompletionChunk;
  content?: string;
  error?: Error;
}
