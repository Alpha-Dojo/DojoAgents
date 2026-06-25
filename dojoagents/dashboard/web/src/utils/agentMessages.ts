import type { AgentChatMessage, AgentChatRole } from '../types/agent';
import { resolveActivitySteps, toolItemsFromSteps } from './agentActivityTimeline';

export type AgentApiMessage = {
  role: AgentChatRole;
  content: string;
};

function assistantFallbackContent(message: AgentChatMessage, fallback: string): string {
  const steps = resolveActivitySteps(message);
  if (toolItemsFromSteps(steps).length > 0) return fallback;
  if (steps.some((step) => step.kind === 'eval')) return fallback;
  const thinkText = steps
    .filter((step): step is Extract<typeof step, { kind: 'think' }> => step.kind === 'think')
    .map((step) => step.block.text.trim())
    .filter(Boolean)
    .join('\n\n');
  if (thinkText) return thinkText;
  return fallback;
}

/** Drop the trailing in-progress assistant bubble before writing to session storage. */
export function messagesForSessionPersist(messages: AgentChatMessage[]): AgentChatMessage[] {
  if (messages.length === 0) return messages;
  const last = messages[messages.length - 1];
  if (last.role === 'assistant' && !last.content.trim()) {
    return messages.slice(0, -1);
  }
  return messages;
}

/** Ensure stored UI messages never keep a trailing empty assistant bubble. */
export function finalizeIncompleteAssistantMessages(
  messages: AgentChatMessage[],
  interruptedFallback: string,
): AgentChatMessage[] {
  if (messages.length === 0) return messages;
  const last = messages[messages.length - 1];
  if (last.role !== 'assistant' || last.content.trim()) {
    return messages;
  }
  const content = assistantFallbackContent(last, interruptedFallback);
  return [...messages.slice(0, -1), { ...last, content }];
}

/** Strip UI-only fields and guarantee API payload passes min_length validation. */
export function prepareMessagesForApi(
  messages: AgentChatMessage[],
  assistantFallback: string,
): AgentApiMessage[] {
  const prepared: AgentApiMessage[] = [];
  for (const message of messages) {
    const trimmed = message.content.trim();
    if (trimmed) {
      prepared.push({ role: message.role, content: trimmed });
      continue;
    }
    if (message.role !== 'assistant') {
      continue;
    }
    const fallback = assistantFallbackContent(message, assistantFallback).trim();
    if (fallback) {
      prepared.push({ role: message.role, content: fallback });
    }
  }
  return prepared;
}
