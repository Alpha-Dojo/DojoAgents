import type { AgentChatMessage } from '../types/agent';

export interface AgentConversationCheckpoint {
  id: string;
  messageIndex: number;
  userMessageIndex: number;
  title: string;
  preview: string;
}

interface DeriveCheckpointOptions {
  streamingMessageIndex?: number | null;
}

function firstLine(value: string): string {
  return (
    value
      .split(/\r?\n/)
      .map((line) => line.trim())
      .find(Boolean) ?? ''
  );
}

function truncate(value: string, limit: number): string {
  return value.length > limit ? `${value.slice(0, limit - 1)}…` : value;
}

export function deriveConversationCheckpoints(
  messages: AgentChatMessage[],
  options: DeriveCheckpointOptions = {},
): AgentConversationCheckpoint[] {
  let userTitle = '';
  let userMessageIndex: number | null = null;

  return messages.flatMap((message, messageIndex) => {
    if (message.role === 'user') {
      userTitle = truncate(firstLine(message.content), 56);
      userMessageIndex = messageIndex;
      return [];
    }
    if (messageIndex === options.streamingMessageIndex) return [];

    const assistantPreview = firstLine(message.content);
    const hasActivity = Boolean(message.activitySteps?.length);
    if (!assistantPreview && !hasActivity) return [];

    const title = userTitle || 'Conversation checkpoint';
    return [
      {
        id: `checkpoint-${messageIndex}`,
        messageIndex,
        userMessageIndex: userMessageIndex ?? messageIndex,
        title,
        preview: truncate(assistantPreview || title, 140),
      },
    ];
  });
}

export function checkpointTickWidth(distance: number): number {
  return [30, 23, 17, 13][distance] ?? 9;
}
