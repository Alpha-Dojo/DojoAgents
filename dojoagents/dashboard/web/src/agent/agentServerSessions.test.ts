import assert from 'node:assert/strict';
import test from 'node:test';

import type {
  AgentServerSessionMessagesResponse,
  AgentServerSessionSummary,
  AgentSession,
} from '../types/agent.ts';
import {
  appendMissingServerSessions,
  fallbackActivityStepsFromMessages,
  serverMessagesToAgentMessages,
  serverTurnToActivitySteps,
} from './agentServerSessions.ts';
import { getExpandableToolResultContent } from '../utils/agentToolDetail.ts';

function serverSession(
  sessionId: string,
  overrides: Partial<AgentServerSessionSummary> = {},
): AgentServerSessionSummary {
  return {
    session_id: sessionId,
    agent_id: 'dojo-agent',
    title: `Server ${sessionId}`,
    user_id: 'anonymous',
    channel: 'dashboard',
    model: 'openai',
    locale: 'zh',
    created_at: '2026-07-13T01:00:00Z',
    updated_at: '2026-07-13T02:00:00Z',
    message_count: 2,
    turn_count: 1,
    run_count: 1,
    status: 'idle',
    archived: false,
    ...overrides,
  };
}

test('adds missing server sessions without overwriting local sessions', () => {
  const local: AgentSession = {
    id: 'shared',
    title: 'Local title',
    modelId: 'local-model',
    messages: [{ role: 'user', content: 'local message' }],
    createdAt: 1,
    updatedAt: 2,
  };

  const merged = appendMissingServerSessions(
    [local],
    [serverSession('shared'), serverSession('server-only')],
  );

  assert.equal(merged.length, 2);
  assert.equal(merged.find((session) => session.id === 'shared'), local);
  assert.deepEqual(
    merged.find((session) => session.id === 'server-only'),
    {
      id: 'server-only',
      title: 'Server server-only',
      modelId: 'openai',
      messages: [],
      createdAt: Date.parse('2026-07-13T01:00:00Z'),
      updatedAt: Date.parse('2026-07-13T02:00:00Z'),
      source: 'server',
      messagesHydrated: false,
      activityHydrated: false,
      activityHydrationVersion: undefined,
      revision: 1,
    },
  );
});

test('rebuilds tool calls and aggregated role tool results from messages', () => {
  const messages: AgentServerSessionMessagesResponse['messages'] = [
    { message_id: 0, role: 'user', content: 'inspect', created_at: '', updated_at: '', raw: {} },
    {
      message_id: 1,
      role: 'assistant',
      content: '',
      created_at: '',
      updated_at: '',
      raw: {
        role: 'assistant',
        tool_calls: [{
          id: 'call-1',
          function: { name: 'portfolio_read_list', arguments: '{"pinned":true}' },
        }],
      },
    },
    {
      message_id: 2,
      role: 'tool',
      content: 'result one',
      created_at: '',
      updated_at: '',
      raw: { role: 'tool', tool_call_id: 'call-1', name: 'portfolio_read_list', content: 'result one' },
      openai_messages: [
        { role: 'tool', tool_call_id: 'call-1', name: 'portfolio_read_list', content: 'result one' },
        { role: 'tool', tool_call_id: 'call-2', name: 'execute_code', content: 'result two' },
      ],
      raw_strands: {
        role: 'user',
        content: [
          { toolResult: { toolUseId: 'call-1', status: 'success' } },
          { toolResult: { toolUseId: 'call-2', status: 'error' } },
        ],
      },
    },
    { message_id: 3, role: 'assistant', content: 'done', created_at: '', updated_at: '', raw: {} },
  ];

  const fallback = fallbackActivityStepsFromMessages(messages);
  assert.equal(fallback[0]?.length, 3);
  assert.equal(fallback[0]?.[0]?.kind === 'tool' && fallback[0][0].item.tool, 'portfolio_read_list');
  assert.equal(fallback[0]?.[0]?.kind === 'tool' && fallback[0][0].item.status, 'done');
  assert.deepEqual(
    fallback[0]?.[0]?.kind === 'tool' && fallback[0][0].item.arguments,
    { pinned: true },
  );
  assert.equal(fallback[0]?.[1]?.kind === 'tool' && fallback[0][1].item.tool, 'execute_code');
  assert.equal(fallback[0]?.[1]?.kind === 'tool' && fallback[0][1].item.status, 'error');

  const projected = serverMessagesToAgentMessages({
    session_id: 'session',
    agent_id: 'dojo-agent',
    messages,
    next_offset: null,
  });
  assert.deepEqual(projected.map((message) => message.role), ['user', 'assistant']);
  assert.equal(projected[1]?.activitySteps?.length, 3);

  const projectedWithPartialEvents = serverMessagesToAgentMessages({
    session_id: 'session',
    agent_id: 'dojo-agent',
    messages,
    next_offset: null,
    turns: [{ events: [
      { type: 'think_start' },
      { type: 'think_delta', text: 'reasoning' },
      { type: 'think_end' },
    ] }],
  });
  assert.deepEqual(
    projectedWithPartialEvents[1]?.activitySteps?.map((step) => step.kind),
    ['think', 'tool', 'tool', 'text'],
  );
});

test('enriches event tool cards with message result content for expansion', () => {
  const response: AgentServerSessionMessagesResponse = {
    session_id: 'event-and-message',
    agent_id: 'dojo-agent',
    next_offset: null,
    turns: [{ events: [
      { type: 'tool_start', call_id: 'call-1', tool: 'portfolio_read_detail', arguments: { portfolio_id: 'p-1' } },
      { type: 'tool_result', call_id: 'call-1', tool: 'portfolio_read_detail', ok: true, latency_ms: 12 },
    ] }],
    messages: [
      { message_id: 0, role: 'user', content: '查看组合', created_at: '', updated_at: '', raw: {} },
      {
        message_id: 1,
        role: 'assistant',
        content: '',
        created_at: '',
        updated_at: '',
        raw: { role: 'assistant', tool_calls: [{ id: 'call-1', function: { name: 'portfolio_read_detail', arguments: '{"portfolio_id":"p-1"}' } }] },
      },
      {
        message_id: 2,
        role: 'tool',
        content: '{"id":"p-1","positions":[{"ticker":"MSFT"}]}',
        created_at: '',
        updated_at: '',
        raw: { role: 'tool', tool_call_id: 'call-1', name: 'portfolio_read_detail', content: '{"id":"p-1"}' },
      },
      { message_id: 3, role: 'assistant', content: '组合分析完成。', created_at: '', updated_at: '', raw: {} },
    ],
  };

  const projected = serverMessagesToAgentMessages(response);
  const tool = projected[1]?.activitySteps?.find((step) => step.kind === 'tool');
  assert.equal(
    tool?.kind === 'tool' && tool.item.resultContent,
    '{"id":"p-1","positions":[{"ticker":"MSFT"}]}',
  );
  assert.equal(
    tool?.kind === 'tool' && getExpandableToolResultContent(
      tool.item.tool,
      tool.item.resultContent,
      tool.item.showRawResultContent,
    ),
    '{"id":"p-1","positions":[{"ticker":"MSFT"}]}',
  );
  assert.equal(
    tool?.kind === 'tool' && getExpandableToolResultContent(tool.item.tool, tool.item.resultContent),
    null,
  );
});

test('uses backend-projected viz blocks for historical tool cards', () => {
  const vizBlock = {
    id: 'portfolio-list-1',
    kind: 'table' as const,
    title: 'Portfolios',
    source_tool: 'portfolio_read_list',
    truncated: false,
    payload: { columns: [], rows: [{ id: 'p-1', name: 'Core' }] },
  };
  const response: AgentServerSessionMessagesResponse = {
    session_id: 'history-viz',
    agent_id: 'dojo-agent',
    next_offset: null,
    messages: [
      { message_id: 0, role: 'user', content: '查看组合', created_at: '', updated_at: '', raw: {} },
      {
        message_id: 1,
        role: 'tool',
        content: '[{"id":"p-1","name":"Core"}]',
        created_at: '',
        updated_at: '',
        raw: { role: 'tool', tool_call_id: 'call-1', name: 'portfolio_read_list' },
        tool_results: [{
          call_id: 'call-1',
          tool: 'portfolio_read_list',
          content: '[{"id":"p-1","name":"Core"}]',
          data: { items: [{ id: 'p-1', name: 'Core' }] },
          viz_blocks: [vizBlock],
        }],
      },
      { message_id: 2, role: 'assistant', content: '读取完成。', created_at: '', updated_at: '', raw: {} },
    ],
  };

  const projected = serverMessagesToAgentMessages(response);
  const tool = projected[1]?.activitySteps?.find((step) => step.kind === 'tool');
  assert.deepEqual(tool?.kind === 'tool' && tool.item.vizBlocks, [vizBlock]);
  assert.deepEqual(tool?.kind === 'tool' && tool.item.data, { items: [{ id: 'p-1', name: 'Core' }] });
});

test('folds intermediate assistant messages into one ordered local-style turn', () => {
  const response: AgentServerSessionMessagesResponse = {
    session_id: 'multi-step',
    agent_id: 'dojo-agent',
    next_offset: null,
    messages: [
      { message_id: 0, role: 'user', content: '分析股票', created_at: '', updated_at: '', raw: {} },
      {
        message_id: 1,
        role: 'assistant',
        content: '我先查看持仓。',
        created_at: '',
        updated_at: '',
        raw: {
          role: 'assistant',
          tool_calls: [{ id: 'call-1', function: { name: 'portfolio_read_list', arguments: '{}' } }],
        },
      },
      {
        message_id: 2,
        role: 'tool',
        content: 'portfolio result',
        created_at: '',
        updated_at: '',
        raw: { role: 'tool', tool_call_id: 'call-1', name: 'portfolio_read_list', content: 'portfolio result' },
      },
      {
        message_id: 3,
        role: 'assistant',
        content: '接着获取行情。',
        created_at: '',
        updated_at: '',
        raw: {
          role: 'assistant',
          tool_calls: [{ id: 'call-2', function: { name: 'get_price', arguments: '{"ticker":"MSFT"}' } }],
        },
      },
      {
        message_id: 4,
        role: 'tool',
        content: 'price result',
        created_at: '',
        updated_at: '',
        raw: { role: 'tool', tool_call_id: 'call-2', name: 'get_price', content: 'price result' },
      },
      { message_id: 5, role: 'assistant', content: '这是最终分析。', created_at: '', updated_at: '', raw: {} },
    ],
  };

  const projected = serverMessagesToAgentMessages(response);
  assert.equal(projected.length, 2);
  assert.equal(projected[0]?.content, '分析股票');
  assert.equal(projected[1]?.content, '这是最终分析。');
  assert.deepEqual(
    projected[1]?.activitySteps?.map((step) =>
      step.kind === 'text' ? `text:${step.text}` : step.kind === 'tool' ? `tool:${step.item.tool}` : step.kind
    ),
    [
      'text:我先查看持仓。',
      'tool:portfolio_read_list',
      'text:接着获取行情。',
      'tool:get_price',
      'text:这是最终分析。',
    ],
  );
});

test('projects only displayable user and assistant server messages', () => {
  const response: AgentServerSessionMessagesResponse = {
    session_id: 'server-only',
    agent_id: 'dojo-agent',
    next_offset: null,
    messages: [
      { message_id: 1, role: 'user', content: 'hello', created_at: '', updated_at: '', raw: {} },
      { message_id: 2, role: 'tool', content: 'hidden', created_at: '', updated_at: '', raw: {} },
      { message_id: 3, role: 'assistant', content: 'hi', created_at: '', updated_at: '', raw: {} },
    ],
  };

  const projected = serverMessagesToAgentMessages(response);
  assert.deepEqual(projected.map(({ role, content }) => ({ role, content })), [
    { role: 'user', content: 'hello' },
    { role: 'assistant', content: 'hi' },
  ]);
  assert.equal(projected[1]?.activitySteps?.[0]?.kind, 'text');
});

test('rebuilds thinking and tool activity with the local activity step shape', () => {
  const steps = serverTurnToActivitySteps({
    events: [
      { type: 'think_start' },
      { type: 'think_delta', text: 'Inspect the market first.' },
      { type: 'think_end' },
      { type: 'tool_start', call_id: 'call-1', tool: 'market_overview', arguments: { market: 'US' } },
      {
        type: 'tool_result',
        call_id: 'call-1',
        tool: 'market_overview',
        ok: true,
        latency_ms: 24,
        content: 'complete',
        data: { count: 3 },
      },
      { type: 'delta', text: 'The market is higher.' },
    ],
  });

  assert.equal(steps[0]?.kind, 'think');
  assert.equal(steps[0]?.kind === 'think' && steps[0].block.text, 'Inspect the market first.');
  assert.equal(steps[0]?.kind === 'think' && steps[0].block.done, true);
  const tool = steps[1]?.kind === 'tool' ? steps[1].item : null;
  assert.equal(tool?.callId, 'call-1');
  assert.equal(tool?.tool, 'market_overview');
  assert.equal(tool?.status, 'done');
  assert.equal(tool?.latencyMs, 24);
  assert.deepEqual(tool?.data, { count: 3 });
  assert.equal(tool?.resultContent, 'complete');
  assert.deepEqual(tool?.arguments, { market: 'US' });
  assert.equal(steps[2]?.kind === 'text' && steps[2].text, 'The market is higher.');
});

test('restores viz blocks from turn tool_trace when events omit them', () => {
  const vizBlock = {
    id: 'trace-viz',
    kind: 'kpi_row' as const,
    title: 'Portfolio',
    source_tool: 'portfolio_read_detail',
    truncated: false,
    payload: { items: [{ label: 'Positions', value: 3 }] },
  };
  const steps = serverTurnToActivitySteps({
    events: [
      { type: 'tool_start', call_id: 'call-detail', tool: 'portfolio_read_detail', arguments: { portfolio_id: 'p-1' } },
      { type: 'tool_result', call_id: 'call-detail', tool: 'portfolio_read_detail', ok: true },
    ],
    tool_trace: [{
      call_id: 'call-detail',
      tool: 'portfolio_read_detail',
      arguments: { portfolio_id: 'p-1' },
      ok: true,
      data: { id: 'p-1', eval_summary: { position_count: 3 } },
      viz_blocks: [vizBlock],
    }],
  });

  const tool = steps.find((step) => step.kind === 'tool');
  assert.deepEqual(tool?.kind === 'tool' && tool.item.vizBlocks, [vizBlock]);
  assert.deepEqual(
    tool?.kind === 'tool' && tool.item.data,
    { id: 'p-1', eval_summary: { position_count: 3 } },
  );
});
