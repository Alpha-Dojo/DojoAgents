import type {
  AgentChatMessage,
  AgentActivityStep,
  AgentServerSessionEvent,
  AgentServerSessionMessage,
  AgentServerSessionTurn,
  AgentServerSessionSummary,
  AgentServerSessionMessagesResponse,
  AgentSession,
} from '../types/agent';
import {
  appendEvalHint,
  appendTextDelta,
  appendThinkDelta,
  appendThinkEnd,
  appendThinkStart,
  appendToolStart,
  finalizeThinkSteps,
  resolveToolResult,
} from '../utils/agentActivityTimeline';

function parseServerTimestamp(value: string): number {
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) ? timestamp : 0;
}

export function serverSummaryToAgentSession(
  summary: AgentServerSessionSummary,
): AgentSession {
  const createdAt = parseServerTimestamp(summary.created_at);
  const updatedAt = parseServerTimestamp(summary.updated_at) || createdAt;
  return {
    id: summary.session_id,
    title: summary.title || summary.session_id,
    modelId: summary.model,
    messages: [],
    createdAt,
    updatedAt,
    source: 'server',
    messagesHydrated: summary.message_count === 0,
    activityHydrated: summary.message_count === 0,
    activityHydrationVersion: summary.message_count === 0 ? 7 : undefined,
    revision: 1,
  };
}

export function appendMissingServerSessions(
  localSessions: AgentSession[],
  serverSessions: AgentServerSessionSummary[],
): AgentSession[] {
  const localIds = new Set(localSessions.map((session) => session.id));
  const missing = serverSessions
    .filter((session) => !localIds.has(session.session_id))
    .map(serverSummaryToAgentSession);
  return [...localSessions, ...missing].sort((left, right) => right.updatedAt - left.updatedAt);
}

export function serverMessagesToAgentMessages(
  response: AgentServerSessionMessagesResponse,
): AgentChatMessage[] {
  const fallbackTurns = fallbackActivityStepsFromMessages(response.messages);
  const conversationTurns = groupServerConversationTurns(response.messages);
  const turns = response.turns ?? [];
  return conversationTurns.flatMap((conversation, turnIndex): AgentChatMessage[] => {
    const projected: AgentChatMessage[] = [];
    if (conversation.userContent !== null) {
      projected.push({ role: 'user', content: conversation.userContent });
    }
    const eventSteps = serverTurnToActivitySteps(turns[turnIndex]);
    const activitySteps = mergeFallbackToolSteps(
      eventSteps,
      fallbackTurns[turnIndex] ?? [],
    );
    if (conversation.assistantContent !== null || activitySteps.length > 0) {
      projected.push({
        role: 'assistant',
        content: conversation.assistantContent ?? '',
        ...(activitySteps.length > 0 ? { activitySteps } : {}),
      });
    }
    return projected;
  });
}

interface ServerConversationTurn {
  userContent: string | null;
  assistantContent: string | null;
}

function groupServerConversationTurns(
  messages: AgentServerSessionMessage[],
): ServerConversationTurn[] {
  const turns: ServerConversationTurn[] = [];
  let current: ServerConversationTurn | null = null;
  const ensureTurn = () => {
    if (current) return current;
    current = { userContent: null, assistantContent: null };
    turns.push(current);
    return current;
  };
  for (const message of messages) {
    if (message.role === 'user') {
      current = { userContent: message.content, assistantContent: null };
      turns.push(current);
    } else if (message.role === 'assistant' && message.content.trim()) {
      // Intermediate assistant messages are represented in activitySteps; the
      // latest assistant text is the final answer for this user turn.
      ensureTurn().assistantContent = message.content;
    }
  }
  return turns;
}

function mergeFallbackToolSteps(
  eventSteps: AgentActivityStep[],
  fallbackSteps: AgentActivityStep[],
): AgentActivityStep[] {
  let merged = [...eventSteps];
  const eventHasText = eventSteps.some((step) => step.kind === 'text');
  for (const fallback of fallbackSteps) {
    if (fallback.kind === 'text') {
      if (!eventHasText) merged.push(fallback);
      continue;
    }
    if (fallback.kind !== 'tool') continue;
    const existingIndex = merged.findIndex((step) =>
      step.kind === 'tool' && (
        (fallback.item.callId && step.item.callId === fallback.item.callId) ||
        (!fallback.item.callId && step.item.tool === fallback.item.tool)
      ));
    if (existingIndex < 0) {
      merged.push(fallback);
    } else if (
      merged[existingIndex]?.kind === 'tool' &&
      merged[existingIndex].item.status === 'running'
    ) {
      merged = merged.map((step, index) => index === existingIndex ? fallback : step);
    } else if (merged[existingIndex]?.kind === 'tool') {
      const existing = merged[existingIndex];
      merged = merged.map((step, index) => index === existingIndex ? {
        ...existing,
        item: {
          ...fallback.item,
          ...existing.item,
          arguments: existing.item.arguments ?? fallback.item.arguments,
          data: existing.item.data ?? fallback.item.data,
          resultSummary: existing.item.resultSummary ?? fallback.item.resultSummary,
          resultContent: existing.item.resultContent ?? fallback.item.resultContent,
          vizBlocks: existing.item.vizBlocks ?? fallback.item.vizBlocks,
        },
      } : step);
    }
  }
  return merged;
}

interface ToolCallProjection {
  callId?: string;
  tool: string;
  arguments: Record<string, unknown>;
}

interface ToolResultProjection {
  callId?: string;
  tool: string;
  content: string;
  ok: boolean;
  data?: Record<string, unknown> | null;
  vizBlocks?: import('../types/agentViz').AgentVizBlock[];
}

function objectRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function parseArguments(value: unknown): Record<string, unknown> {
  if (typeof value !== 'string') return objectRecord(value) ?? {};
  try {
    return objectRecord(JSON.parse(value)) ?? {};
  } catch {
    return {};
  }
}

function toolCallsFromMessage(message: AgentServerSessionMessage): ToolCallProjection[] {
  const rawCalls = message.raw.tool_calls;
  if (Array.isArray(rawCalls)) {
    return rawCalls.flatMap((rawCall): ToolCallProjection[] => {
      const call = objectRecord(rawCall);
      const fn = objectRecord(call?.function);
      if (!fn) return [];
      return [{
        callId: typeof call?.id === 'string' ? call.id : undefined,
        tool: typeof fn.name === 'string' ? fn.name : 'unknown',
        arguments: parseArguments(fn.arguments),
      }];
    });
  }
  const content = message.raw_strands?.content;
  if (!Array.isArray(content)) return [];
  return content.flatMap((block): ToolCallProjection[] => {
    const toolUse = objectRecord(objectRecord(block)?.toolUse);
    if (!toolUse) return [];
    return [{
      callId: typeof toolUse.toolUseId === 'string' ? toolUse.toolUseId : undefined,
      tool: typeof toolUse.name === 'string' ? toolUse.name : 'unknown',
      arguments: objectRecord(toolUse.input) ?? {},
    }];
  });
}

function toolResultStatuses(message: AgentServerSessionMessage): Map<string, boolean> {
  const statuses = new Map<string, boolean>();
  const content = message.raw_strands?.content;
  if (!Array.isArray(content)) return statuses;
  for (const block of content) {
    const result = objectRecord(objectRecord(block)?.toolResult);
    if (!result || typeof result.toolUseId !== 'string') continue;
    statuses.set(result.toolUseId, result.status !== 'error');
  }
  return statuses;
}

function toolResultsFromMessage(message: AgentServerSessionMessage): ToolResultProjection[] {
  const statuses = toolResultStatuses(message);
  if (message.tool_results?.length) {
    return message.tool_results.map((result) => ({
      callId: result.call_id || undefined,
      tool: result.tool || 'unknown',
      content: result.content,
      ok: result.call_id ? statuses.get(result.call_id) !== false : true,
      data: result.data ?? null,
      vizBlocks: result.viz_blocks,
    }));
  }
  const projected = message.openai_messages?.length
    ? message.openai_messages
    : [message.raw];
  return projected.flatMap((rawResult): ToolResultProjection[] => {
    const result = objectRecord(rawResult);
    if (result?.role !== 'tool') return [];
    const callId = typeof result.tool_call_id === 'string' ? result.tool_call_id : undefined;
    const projectedContent = typeof result.content === 'string' ? result.content : '';
    const content = projected.length === 1 && message.content.length > projectedContent.length
      ? message.content
      : projectedContent;
    return [{
      callId,
      tool: typeof result.name === 'string' ? result.name : 'unknown',
      content,
      ok: callId ? statuses.get(callId) !== false : true,
      data: null,
      vizBlocks: undefined,
    }];
  });
}

export function fallbackActivityStepsFromMessages(
  messages: AgentServerSessionMessage[],
): AgentActivityStep[][] {
  const turns: AgentActivityStep[][] = [];
  let current = -1;
  const ensureTurn = () => {
    if (current >= 0) return;
    turns.push([]);
    current = 0;
  };
  for (const message of messages) {
    if (message.role === 'user') {
      turns.push([]);
      current = turns.length - 1;
      continue;
    }
    ensureTurn();
    if (message.role === 'assistant' && message.content) {
      turns[current] = appendTextDelta(turns[current], message.content);
    }
    for (const call of toolCallsFromMessage(message)) {
      turns[current] = appendToolStart(
        turns[current],
        call.tool,
        call.arguments,
        call.callId,
      );
    }
    for (const result of toolResultsFromMessage(message)) {
      turns[current] = resolveToolResult(
        turns[current],
        result.tool,
        result.ok,
        0,
        'zh',
        result.ok ? null : result.content,
        result.content,
        result.data ?? null,
        result.vizBlocks,
        result.callId,
      );
      if (result.tool.startsWith('portfolio_read_')) {
        turns[current] = turns[current].map((step) =>
          step.kind === 'tool' && (
            (result.callId && step.item.callId === result.callId) ||
            (!result.callId && step.item.tool === result.tool)
          )
            ? { ...step, item: { ...step.item, showRawResultContent: true } }
            : step,
        );
      }
    }
  }
  return turns;
}

function recordOrNull(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function applyServerEvent(
  state: { steps: AgentActivityStep[]; thinkId: string | null },
  event: AgentServerSessionEvent,
): void {
  if (event.type === 'delta') {
    state.steps = appendTextDelta(state.steps, event.text ?? '');
  } else if (event.type === 'think_start') {
    const next = appendThinkStart(state.steps, state.thinkId);
    state.steps = next.steps;
    state.thinkId = next.currentThinkId;
  } else if (event.type === 'think_delta') {
    state.steps = appendThinkDelta(state.steps, state.thinkId, event.text ?? '');
  } else if (event.type === 'think_end') {
    state.steps = appendThinkEnd(state.steps, state.thinkId);
    state.thinkId = null;
  } else if (event.type === 'tool_start') {
    state.steps = appendToolStart(
      state.steps,
      event.tool ?? 'unknown',
      event.arguments ?? {},
      event.call_id,
    );
  } else if (event.type === 'tool_result') {
    state.steps = resolveToolResult(
      state.steps,
      event.tool ?? 'unknown',
      event.ok !== false,
      event.latency_ms ?? 0,
      'zh',
      event.error,
      event.content,
      recordOrNull(event.data),
      event.viz_blocks,
      event.call_id,
    );
  } else if (event.type === 'eval_hint') {
    state.steps = appendEvalHint(state.steps, event.issues ?? []);
  }
}

export function serverTurnToActivitySteps(
  turn: AgentServerSessionTurn | undefined,
): AgentActivityStep[] {
  if (!turn) return [];
  const state: { steps: AgentActivityStep[]; thinkId: string | null } = {
    steps: [],
    thinkId: null,
  };
  for (const event of turn.events ?? []) applyServerEvent(state, event);
  let traceSteps: AgentActivityStep[] = [];
  for (const trace of turn.tool_trace ?? []) {
    const tool = trace.tool ?? 'unknown';
    traceSteps = appendToolStart(
      traceSteps,
      tool,
      trace.arguments ?? {},
      trace.call_id,
    );
    traceSteps = resolveToolResult(
      traceSteps,
      tool,
      trace.ok !== false,
      trace.latency_ms ?? 0,
      'zh',
      trace.error,
      trace.content,
      trace.data ?? null,
      trace.viz_blocks,
      trace.call_id,
    );
  }
  return finalizeThinkSteps(mergeFallbackToolSteps(state.steps, traceSteps));
}
