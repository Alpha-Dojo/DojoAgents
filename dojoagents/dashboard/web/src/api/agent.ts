import { ApiError } from './http';
import type { AgentChatRequest, AgentModelsResponse, AgentStreamEvent } from '../types/agent';

const API_PREFIX = '/api/v1';

export async function fetchAgentModels(): Promise<AgentModelsResponse> {
  const res = await fetch(`${API_PREFIX}/agent/models`, {
    headers: { Accept: 'application/json' },
  });
  if (!res.ok) {
    throw new ApiError(`Request failed: ${res.status} ${res.statusText}`, res.status);
  }
  return res.json() as Promise<AgentModelsResponse>;
}

function parseSseBlock(block: string): AgentStreamEvent | null {
  const dataLine = block
    .split('\n')
    .map((line) => line.trim())
    .find((line) => line.startsWith('data:'));
  if (!dataLine) return null;
  const raw = dataLine.slice(5).trim();
  if (!raw) return null;
  return JSON.parse(raw) as AgentStreamEvent;
}

async function readErrorMessage(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: string | { msg?: string }[] };
    if (typeof body.detail === 'string') return body.detail;
    if (Array.isArray(body.detail) && body.detail[0]?.msg) return body.detail[0].msg;
  } catch {
    // ignore
  }
  return `Request failed: ${res.status} ${res.statusText}`;
}

export async function streamAgentChat(
  body: AgentChatRequest,
  handlers: {
    onDelta: (text: string) => void;
    onDone: (modelId: string) => void;
    onError: (message: string) => void;
  },
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API_PREFIX}/agent/chat/stream`, {
    method: 'POST',
    headers: {
      Accept: 'text/event-stream',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
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

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    let readResult: ReadableStreamReadResult<Uint8Array>;
    try {
      readResult = await reader.read();
    } catch (err) {
      if (signal?.aborted) return;
      handlers.onError(err instanceof Error ? err.message : 'Stream read failed');
      return;
    }

    const { done, value } = readResult;
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split('\n\n');
    buffer = blocks.pop() ?? '';

    for (const block of blocks) {
      const event = parseSseBlock(block);
      if (!event) continue;
      if (event.type === 'delta') {
        handlers.onDelta(event.text);
      } else if (event.type === 'done') {
        handlers.onDone(event.model_id);
        return;
      } else if (event.type === 'error') {
        handlers.onError(event.message);
        return;
      }
    }
  }

  handlers.onError('Stream ended unexpectedly');
}
