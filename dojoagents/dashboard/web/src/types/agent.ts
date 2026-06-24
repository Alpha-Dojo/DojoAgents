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

export interface AgentChatMessage {
  role: AgentChatRole;
  content: string;
}

export interface AgentChatRequest {
  model_id: string;
  messages: AgentChatMessage[];
}

export interface AgentChatResponse {
  model_id: string;
  message: AgentChatMessage;
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
  | { type: 'done'; model_id: string }
  | { type: 'error'; message: string };
