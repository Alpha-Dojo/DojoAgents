import type { AgentVizBlock } from '../types/agentViz';
import type {
  AgentActivityStep,
  AgentChatMessage,
  AgentEvalHintItem,
  AgentThinkBlock,
  AgentToolActivityItem,
} from '../types/agent';
import { formatToolResultData } from './agentToolDetail';
import { createRandomId } from './randomId';

function findLastRunningToolIndex(
  steps: AgentActivityStep[],
  tool: string,
  callId?: string,
): number {
  if (callId) {
    for (let index = steps.length - 1; index >= 0; index -= 1) {
      const step = steps[index];
      if (step.kind === 'tool' && step.item.callId === callId && step.item.status === 'running') {
        return index;
      }
    }
  }
  for (let index = steps.length - 1; index >= 0; index -= 1) {
    const step = steps[index];
    if (step.kind === 'tool' && step.item.tool === tool && step.item.status === 'running') {
      return index;
    }
  }
  return -1;
}

/** Normalize legacy messages (separate arrays) into a single timeline. */
export function resolveActivitySteps(message: AgentChatMessage): AgentActivityStep[] {
  if (message.activitySteps?.length) {
    return message.activitySteps;
  }

  const steps: AgentActivityStep[] = [];
  for (const block of message.thinkBlocks ?? []) {
    steps.push({ kind: 'think', id: block.id, block });
  }
  for (const hint of message.evalHints ?? []) {
    steps.push({ kind: 'eval', id: hint.id, hint });
  }
  for (const item of message.toolActivity ?? []) {
    steps.push({ kind: 'tool', id: createRandomId(), item });
  }
  return steps;
}

export function messageHasAssistantActivity(message: AgentChatMessage): boolean {
  const steps = resolveActivitySteps(message);
  return steps.length > 0 || Boolean(message.content.trim());
}

export function toolItemsFromSteps(steps: AgentActivityStep[]): AgentToolActivityItem[] {
  return steps.filter((step): step is Extract<AgentActivityStep, { kind: 'tool' }> => step.kind === 'tool').map(
    (step) => step.item,
  );
}

export function appendTextDelta(
  steps: AgentActivityStep[],
  text: string,
): AgentActivityStep[] {
  if (!text) return steps;
  const last = steps.at(-1);
  if (last?.kind === 'text') {
    return steps.map((step, index) =>
      index === steps.length - 1 && step.kind === 'text'
        ? { ...step, text: step.text + text }
        : step,
    );
  }
  return [...steps, { kind: 'text', id: createRandomId(), text }];
}

export function hasOrderedTextSteps(steps: AgentActivityStep[]): boolean {
  return steps.some((step) => step.kind === 'text');
}

export function appendThinkStart(
  steps: AgentActivityStep[],
  currentThinkId: string | null,
): { steps: AgentActivityStep[]; currentThinkId: string } {
  let nextSteps = steps;
  if (currentThinkId) {
    nextSteps = nextSteps.map((step) =>
      step.kind === 'think' && step.id === currentThinkId
        ? { ...step, block: { ...step.block, done: true, collapsed: true } }
        : step,
    );
  }
  const thinkId = createRandomId();
  const block: AgentThinkBlock = {
    id: thinkId,
    text: '',
    collapsed: false,
    done: false,
  };
  return {
    steps: [...nextSteps, { kind: 'think', id: thinkId, block }],
    currentThinkId: thinkId,
  };
}

export function appendThinkDelta(
  steps: AgentActivityStep[],
  currentThinkId: string | null,
  text: string,
): AgentActivityStep[] {
  if (!currentThinkId || !text) return steps;
  return steps.map((step) =>
    step.kind === 'think' && step.id === currentThinkId
      ? { ...step, block: { ...step.block, text: step.block.text + text } }
      : step,
  );
}

export function appendThinkEnd(
  steps: AgentActivityStep[],
  currentThinkId: string | null,
): AgentActivityStep[] {
  if (!currentThinkId) return steps;
  return steps.map((step) =>
    step.kind === 'think' && step.id === currentThinkId
      ? { ...step, block: { ...step.block, done: true, collapsed: true } }
      : step,
  );
}

export function finalizeThinkSteps(steps: AgentActivityStep[]): AgentActivityStep[] {
  return steps
    .filter((step) => step.kind !== 'think' || step.block.text.trim().length > 0)
    .map((step) =>
      step.kind === 'think'
        ? { ...step, block: { ...step.block, done: true, collapsed: true } }
        : step,
    );
}

export function resolveCurrentThinkId(steps: AgentActivityStep[]): string | null {
  for (let index = steps.length - 1; index >= 0; index -= 1) {
    const step = steps[index];
    if (step.kind === 'think' && !step.block.done) {
      return step.id;
    }
  }
  return null;
}

export function appendToolStart(
  steps: AgentActivityStep[],
  tool: string,
  args: Record<string, unknown>,
  callId?: string,
): AgentActivityStep[] {
  return [
    ...steps,
    {
      kind: 'tool',
      id: createRandomId(),
      item: { callId, tool, status: 'running', arguments: args },
    },
  ];
}

export function resolveToolResult(
  steps: AgentActivityStep[],
  tool: string,
  ok: boolean,
  latencyMs: number,
  locale: 'zh' | 'en',
  error?: string | null,
  content?: string | null,
  data?: Record<string, unknown> | null,
  vizBlocks?: AgentVizBlock[],
  callId?: string,
): AgentActivityStep[] {
  const runningIndex = findLastRunningToolIndex(steps, tool, callId);
  const resultSummary = ok ? formatToolResultData(data, locale) : null;
  const nextItem: AgentToolActivityItem = {
    callId,
    tool,
    status: ok ? 'done' : 'error',
    latencyMs,
    error: ok ? null : error ?? null,
    data: ok ? data ?? null : null,
    resultSummary,
    resultContent: ok ? content ?? null : null,
    vizBlocks: ok && vizBlocks?.length ? vizBlocks : undefined,
    arguments: runningIndex >= 0 && steps[runningIndex]?.kind === 'tool'
      ? steps[runningIndex].item.arguments
      : undefined,
  };

  if (runningIndex >= 0) {
    const runningStep = steps[runningIndex];
    if (runningStep.kind !== 'tool') {
      return [...steps, { kind: 'tool', id: createRandomId(), item: nextItem }];
    }
    return steps.map((step, index) =>
      index === runningIndex && step.kind === 'tool'
        ? { ...step, item: { ...step.item, ...nextItem } }
        : step,
    );
  }

  return [...steps, { kind: 'tool', id: createRandomId(), item: nextItem }];
}

export function appendEvalHint(steps: AgentActivityStep[], issues: string[]): AgentActivityStep[] {
  if (issues.length === 0) return steps;
  const key = issues.join('\u0001');
  if (
    steps.some(
      (step) => step.kind === 'eval' && step.hint.issues.join('\u0001') === key,
    )
  ) {
    return steps;
  }
  const hint: AgentEvalHintItem = { id: createRandomId(), issues: [...issues] };
  return [...steps, { kind: 'eval', id: hint.id, hint }];
}

export function toggleThinkStep(
  steps: AgentActivityStep[],
  blockId: string,
): AgentActivityStep[] {
  return steps.map((step) =>
    step.kind === 'think' && step.block.id === blockId
      ? { ...step, block: { ...step.block, collapsed: !step.block.collapsed } }
      : step,
  );
}
