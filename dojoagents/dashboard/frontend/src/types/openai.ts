// OpenAI Chat Completions protocol types

export interface ChatMessage {
  role: 'system' | 'user' | 'assistant' | 'tool'
  content: string | null
  tool_calls?: ToolCall[]
  tool_call_id?: string
}

export interface ToolCall {
  id: string
  type: 'function'
  function: { name: string; arguments: string }
}

export interface ToolDefinition {
  type: 'function'
  function: {
    name: string
    description?: string
    parameters?: Record<string, unknown>
  }
}

export interface ChatCompletionRequest {
  model: string
  messages: ChatMessage[]
  stream?: boolean
  tools?: ToolDefinition[]
  tool_choice?: 'auto' | 'none' | 'required' | object
  temperature?: number
  user?: string
  metadata?: Record<string, unknown>
}

export interface ChatCompletionResponse {
  id: string
  object: 'chat.completion'
  created: number
  model: string
  choices: CompletionChoice[]
  usage: UsageInfo
  // Backward-compat fields from DojoAgents
  content?: string
  session_id?: string
}

export interface CompletionChoice {
  index: number
  message: ChatMessage
  finish_reason: 'stop' | 'tool_calls' | null
}

export interface ChatCompletionChunk {
  id: string
  object: 'chat.completion.chunk'
  created: number
  model: string
  choices: ChunkChoice[]
}

export interface ChunkChoice {
  index: number
  delta: {
    role?: string
    content?: string
    tool_calls?: ToolCall[]
  }
  finish_reason: 'stop' | 'tool_calls' | null
}

export interface UsageInfo {
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
}
