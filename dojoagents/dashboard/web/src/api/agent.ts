import { fetchSettingsConfig } from './settings';
import { ApiError } from './http';
import type {
  AgentChatRequest,
  AgentModelsResponse,
  AgentStreamEvent,
  ChatCompletionChunk,
} from '../types/agent';

const API_URL = '/api/chat';

function providerLabel(provider: string, model: string): string {
  const normalized = provider.trim().toLowerCase();
  if (!normalized) return model;
  return `${normalized}:${model}`;
}

export async function fetchAgentModels(): Promise<AgentModelsResponse> {
  const settings = await fetchSettingsConfig();
  const llmProvider = (settings.llm_provider ?? {}) as {
    default?: string;
    providers?: Record<string, { model?: string }>;
  };
  const agentCfg = (settings.agent ?? {}) as { model?: string };

  const provider = llmProvider.default ?? 'default';
  const providerModel = llmProvider.providers?.[provider]?.model?.trim();
  const agentModel = agentCfg.model?.trim();
  const resolvedModel = agentModel || providerModel || 'gpt-4.1';

  return {
    default_model_id: resolvedModel,
    gemini_configured: true,
    models: [
      {
        id: resolvedModel,
        label: providerLabel(provider, resolvedModel),
        provider,
        available: true,
      },
    ],
  };
}

async function readErrorMessage(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { error?: string; detail?: string | { msg?: string }[] };
    if (typeof body.error === 'string') return body.error;
    if (typeof body.detail === 'string') return body.detail;
    if (Array.isArray(body.detail) && body.detail[0]?.msg) return body.detail[0].msg;
  } catch {
    // ignore
  }
  return `Request failed: ${res.status} ${res.statusText}`;
}

export async function* parseSSEStream(
  response: Response,
): AsyncGenerator<AgentStreamEvent, void, unknown> {
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed || !trimmed.startsWith('data:')) continue;

        const data = trimmed.slice(5).trim();
        if (data === '[DONE]') {
          yield { type: 'done' };
          return;
        }

        try {
          const chunk = JSON.parse(data) as ChatCompletionChunk;
          const delta = chunk.choices[0]?.delta;
          const finishReason = chunk.choices[0]?.finish_reason;

          if (delta?.content) {
            yield { type: 'content_delta', content: delta.content, chunk };
          }
          if (delta?.tool_calls) {
            yield { type: 'tool_call_delta', chunk };
          }
          if (finishReason) {
            yield { type: 'message_end', chunk };
          }
        } catch (e) {
          yield { type: 'error', error: new Error(`SSE parse error: ${e}`) };
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

export async function streamAgentChat(
  body: AgentChatRequest,
  handlers: {
    onEvent: (event: AgentStreamEvent) => void;
    onError: (message: string) => void;
  },
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(API_URL, {
    method: 'POST',
    headers: {
      Accept: 'text/event-stream',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      ...body,
      stream: true,
    }),
    signal,
  });

  if (!res.ok) {
    handlers.onError(await readErrorMessage(res));
    return;
  }

  if (!res.body) {
    handlers.onError('Empty response body');
    return;
  }

  try {
    for await (const event of parseSSEStream(res)) {
      handlers.onEvent(event);
      if (event.type === 'done') return;
      if (event.type === 'error') {
        handlers.onError(event.error?.message ?? 'Stream parse failed');
        return;
      }
    }
  } catch (err) {
    if (signal?.aborted) return;
    const message = err instanceof ApiError ? err.message : err instanceof Error ? err.message : 'Stream failed';
    handlers.onError(message);
    return;
  }

  handlers.onError('Stream ended unexpectedly');
}
