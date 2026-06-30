import type { AgentChatMessage, AgentApiMessage, AgentApiContentPart } from '../types/agent';
import { resolveActivitySteps, toolItemsFromSteps } from './agentActivityTimeline';

export type { AgentApiMessage, AgentApiContentPart };

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

function buildUserApiContent(message: AgentChatMessage): string | AgentApiContentPart[] | null {
  const text = message.content.trim();
  const images = message.images ?? [];
  if (!text && images.length === 0) return null;
  if (images.length === 0) return text;
  const parts: AgentApiContentPart[] = [];
  if (text) {
    parts.push({ type: 'text', text });
  }
  for (const image of images) {
    parts.push({ type: 'image_url', image_url: { url: image.dataUrl } });
  }
  return parts;
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
    if (message.role === 'user') {
      const userContent = buildUserApiContent(message);
      if (userContent) {
        prepared.push({ role: message.role, content: userContent });
      }
      continue;
    }
    const trimmed = message.content.trim();
    if (trimmed) {
      prepared.push({ role: message.role, content: trimmed });
      continue;
    }
    const fallback = assistantFallbackContent(message, assistantFallback).trim();
    if (fallback) {
      prepared.push({ role: message.role, content: fallback });
    }
  }
  return prepared;
}
