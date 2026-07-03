import assert from 'node:assert/strict';
import test from 'node:test';
import type { AgentChatMessage } from '../types/agent.ts';
import {
  checkpointTickWidth,
  deriveConversationCheckpoints,
} from './agentConversationCheckpoints.ts';

test('derives one checkpoint for each completed assistant reply', () => {
  const messages: AgentChatMessage[] = [
    { role: 'user', content: '分析今天的市场\n补充条件' },
    { role: 'assistant', content: '市场整体震荡上行。' },
    { role: 'user', content: '再看风险' },
    { role: 'assistant', content: '主要风险来自波动率。' },
  ];

  assert.deepEqual(deriveConversationCheckpoints(messages), [
    {
      id: 'checkpoint-1',
      messageIndex: 1,
      userMessageIndex: 0,
      title: '分析今天的市场',
      preview: '市场整体震荡上行。',
    },
    {
      id: 'checkpoint-3',
      messageIndex: 3,
      userMessageIndex: 2,
      title: '再看风险',
      preview: '主要风险来自波动率。',
    },
  ]);
});

test('excludes the streaming assistant and empty assistant replies', () => {
  const messages: AgentChatMessage[] = [
    { role: 'user', content: '第一个问题' },
    { role: 'assistant', content: '已完成回答' },
    { role: 'assistant', content: '' },
    { role: 'user', content: '流式问题' },
    { role: 'assistant', content: '仍在生成' },
  ];

  assert.deepEqual(
    deriveConversationCheckpoints(messages, { streamingMessageIndex: 4 }),
    [
      {
        id: 'checkpoint-1',
        messageIndex: 1,
        userMessageIndex: 0,
        title: '第一个问题',
        preview: '已完成回答',
      },
    ],
  );
});

test('uses the user title when assistant content has no plain text', () => {
  const messages: AgentChatMessage[] = [
    { role: 'user', content: '工具执行问题' },
    {
      role: 'assistant',
      content: '',
      activitySteps: [
        {
          kind: 'tool',
          id: 'tool-1',
          item: { tool: 'search', status: 'done' },
        },
      ],
    },
  ];

  assert.deepEqual(deriveConversationCheckpoints(messages), [
    {
      id: 'checkpoint-1',
      messageIndex: 1,
      userMessageIndex: 0,
      title: '工具执行问题',
      preview: '工具执行问题',
    },
  ]);
});

test('falls back to the assistant index when no user message precedes it', () => {
  const messages: AgentChatMessage[] = [
    { role: 'assistant', content: 'Standalone answer' },
  ];

  assert.deepEqual(deriveConversationCheckpoints(messages), [
    {
      id: 'checkpoint-0',
      messageIndex: 0,
      userMessageIndex: 0,
      title: 'Conversation checkpoint',
      preview: 'Standalone answer',
    },
  ]);
});

test('scales tick width by distance from the interactive checkpoint', () => {
  assert.deepEqual(
    [0, 1, 2, 3, 4].map((distance) => checkpointTickWidth(distance)),
    [30, 23, 17, 13, 9],
  );
});
