import { ApiError } from './http';
import type { AgentChatRequest, AgentModelsResponse, AgentStreamEvent } from '../types/agent';
import type { AgentVizBlock } from '../types/agentViz';

const API_PREFIX = '/api/v1';

export type AgentStreamHandlers = {
  onDelta: (text: string) => void;
  onThinkStart?: () => void;
  onThinkDelta?: (text: string) => void;
  onThinkEnd?: () => void;
  onPhase?: (phase: 'planning' | 'tools' | 'answering') => void;
  onRetry?: (payload: { attempt: number; max_attempts: number; text: string }) => void;
  onToolStart?: (tool: string, args: Record<string, unknown>) => void;
  onToolResult?: (payload: {
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
    viz_blocks?: AgentVizBlock[];
  }) => void;
  onEvalHint?: (payload: { text: string; issues: string[] }) => void;
  onDone: (modelId: string) => void;
  onError: (message: string) => void;
};

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
    const body = (await res.json()) as {
      detail?: string | { msg?: string; loc?: (string | number)[] }[];
    };
    if (typeof body.detail === 'string') return body.detail;
    if (Array.isArray(body.detail) && body.detail.length > 0) {
      const first = body.detail[0];
      if (first && typeof first.msg === 'string') {
        if (first.msg.includes('at least 1 character')) {
          return 'Conversation history contains an empty message. Refresh the chat or start a new session.';
        }
        return first.msg;
      }
    }
  } catch {
    // ignore
  }
  return `Request failed: ${res.status} ${res.statusText}`;
}

function dispatchStreamEvent(event: AgentStreamEvent, handlers: AgentStreamHandlers): 'continue' | 'done' | 'error' {
  if (event.type === 'delta') {
    handlers.onDelta(event.text);
    return 'continue';
  }
  if (event.type === 'think_start') {
    handlers.onThinkStart?.();
    return 'continue';
  }
  if (event.type === 'think_delta') {
    handlers.onThinkDelta?.(event.text);
    return 'continue';
  }
  if (event.type === 'think_end') {
    handlers.onThinkEnd?.();
    return 'continue';
  }
  if (event.type === 'phase') {
    handlers.onPhase?.(event.phase);
    return 'continue';
  }
  if (event.type === 'retry') {
    handlers.onRetry?.({
      attempt: event.attempt,
      max_attempts: event.max_attempts,
      text: event.text,
    });
    return 'continue';
  }
  if (event.type === 'tool_start') {
    handlers.onToolStart?.(event.tool, event.arguments);
    return 'continue';
  }
  if (event.type === 'tool_result') {
    handlers.onToolResult?.({
      tool: event.tool,
      ok: event.ok,
      latency_ms: event.latency_ms,
      truncated: event.truncated,
      error: event.error,
      data: event.data,
      viz_blocks: event.viz_blocks,
    });
    return 'continue';
  }
  if (event.type === 'eval_hint') {
    handlers.onEvalHint?.({ text: event.text, issues: event.issues });
    return 'continue';
  }
  if (event.type === 'done') {
    handlers.onDone(event.model_id);
    return 'done';
  }
  if (event.type === 'error') {
    handlers.onError(event.message);
    return 'error';
  }
  return 'continue';
}

export type SseConsumeResult = 'done' | 'error' | 'eof' | 'aborted';

async function consumeSseResponse(
  res: Response,
  handlers: AgentStreamHandlers,
  signal?: AbortSignal,
): Promise<SseConsumeResult> {
  if (!res.ok) {
    handlers.onError(await readErrorMessage(res));
    return 'error';
  }
  if (!res.body) {
    handlers.onError('Empty response body');
    return 'error';
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    let readResult: ReadableStreamReadResult<Uint8Array>;
    try {
      readResult = await reader.read();
    } catch (err) {
      if (signal?.aborted) return 'aborted';
      throw err;
    }

    const { done, value } = readResult;
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split('\n\n');
    buffer = blocks.pop() ?? '';

    for (const block of blocks) {
      const event = parseSseBlock(block);
      if (!event) continue;
      const outcome = dispatchStreamEvent(event, handlers);
      if (outcome === 'done' || outcome === 'error') {
        return outcome;
      }
    }
  }

  return 'eof';
}

export async function createAgentRun(
  body: AgentChatRequest,
): Promise<{ run_id: string; model_id: string }> {
  const res = await fetch(`${API_PREFIX}/agent/runs`, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ use_tools: true, ...body }),
  });
  if (!res.ok) {
    throw new ApiError(await readErrorMessage(res), res.status);
  }
  return res.json() as Promise<{ run_id: string; model_id: string }>;
}

export async function fetchAgentRunStatus(
  runId: string,
): Promise<{ run_id: string; model_id: string; status: string; event_count: number }> {
  const res = await fetch(`${API_PREFIX}/agent/runs/${runId}`, {
    headers: { Accept: 'application/json' },
  });
  if (!res.ok) {
    throw new ApiError(await readErrorMessage(res), res.status);
  }
  return res.json() as Promise<{
    run_id: string;
    model_id: string;
    status: string;
    event_count: number;
  }>;
}

export async function cancelAgentRun(runId: string): Promise<void> {
  const res = await fetch(`${API_PREFIX}/agent/runs/${runId}/cancel`, {
    method: 'POST',
    headers: { Accept: 'application/json' },
  });
  if (!res.ok) {
    throw new ApiError(await readErrorMessage(res), res.status);
  }
}

export async function streamAgentRunEvents(
  runId: string,
  cursor: number,
  handlers: AgentStreamHandlers,
  signal?: AbortSignal,
): Promise<SseConsumeResult> {
  const res = await fetch(`${API_PREFIX}/agent/runs/${runId}/events?cursor=${cursor}`, {
    method: 'GET',
    headers: { Accept: 'text/event-stream' },
    signal,
  });
  return consumeSseResponse(res, handlers, signal);
}

/** @deprecated Prefer createAgentRun + streamAgentRunEvents for UI-decoupled runs. */
export async function streamAgentChat(
  body: AgentChatRequest,
  handlers: AgentStreamHandlers,
  signal?: AbortSignal,
): Promise<SseConsumeResult> {
  const res = await fetch(`${API_PREFIX}/agent/chat/stream`, {
    method: 'POST',
    headers: {
      Accept: 'text/event-stream',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ use_tools: true, ...body }),
    signal,
  });
  return consumeSseResponse(res, handlers, signal);
}
