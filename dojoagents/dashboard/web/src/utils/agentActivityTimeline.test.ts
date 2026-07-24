import assert from 'node:assert/strict';
import test from 'node:test';
import type { AgentActivityStep } from '../types/agent.ts';
import {
  appendTextDelta,
  appendToolStart,
  hasOrderedTextSteps,
  reconcileToolTrace,
  resolveToolResult,
} from './agentActivityTimeline.ts';

test('merges consecutive assistant deltas into one text step', () => {
  const first = appendTextDelta([], '先获取行情数据');
  const second = appendTextDelta(first, '和确认代码。');

  assert.equal(second.length, 1);
  assert.equal(second[0]?.kind, 'text');
  assert.equal(
    second[0]?.kind === 'text' ? second[0].text : '',
    '先获取行情数据和确认代码。',
  );
});

test('keeps text segments on both sides of a tool call', () => {
  let steps: AgentActivityStep[] = appendTextDelta([], '先确认代码。');
  steps = appendToolStart(
    steps,
    'resolve_symbol',
    { query: '长电科技' },
    'call-1',
  );
  steps = resolveToolResult(
    steps,
    'resolve_symbol',
    true,
    12,
    'zh',
    null,
    null,
    { symbol: '600584.SS' },
    undefined,
    'call-1',
  );
  steps = appendTextDelta(steps, '确认代码为 600584.SS。');

  assert.deepEqual(
    steps.map((step) => step.kind),
    ['text', 'tool', 'text'],
  );
  assert.equal(
    steps[1]?.kind === 'tool' ? steps[1].item.status : '',
    'done',
  );
  assert.equal(
    steps[2]?.kind === 'text' ? steps[2].text : '',
    '确认代码为 600584.SS。',
  );
});

test('detects ordered messages without treating legacy activity as ordered text', () => {
  assert.equal(hasOrderedTextSteps(appendTextDelta([], '正文')), true);
  assert.equal(
    hasOrderedTextSteps(appendToolStart([], 'resolve_symbol', {}, 'call-1')),
    false,
  );
});

test('reconciles a running tool from terminal done tool trace', () => {
  const steps = appendToolStart(
    [],
    'portfolio_write_create',
    { name: 'Income' },
    'call-blocked',
  );

  const reconciled = reconcileToolTrace(
    steps,
    [
      {
        call_id: 'call-blocked',
        tool: 'portfolio_write_create',
        arguments: { name: 'Income' },
        ok: false,
        latency_ms: 0,
        truncated: false,
        error: 'Blocked by Harness policy',
      },
    ],
    'en',
  );

  assert.equal(reconciled.length, 1);
  assert.equal(reconciled[0]?.kind, 'tool');
  assert.equal(
    reconciled[0]?.kind === 'tool' ? reconciled[0].item.status : '',
    'error',
  );
  assert.equal(
    reconciled[0]?.kind === 'tool' ? reconciled[0].item.error : '',
    'Blocked by Harness policy',
  );
});

test('does not duplicate a tool already completed by live SSE', () => {
  let steps = appendToolStart([], 'portfolio_read_detail', {}, 'call-1');
  steps = resolveToolResult(
    steps,
    'portfolio_read_detail',
    true,
    12,
    'en',
    null,
    'ok',
    { id: 'p-1' },
    undefined,
    'call-1',
  );

  const reconciled = reconcileToolTrace(
    steps,
    [
      {
        call_id: 'call-1',
        tool: 'portfolio_read_detail',
        arguments: {},
        ok: true,
        latency_ms: 12,
        truncated: false,
        data: { id: 'p-1' },
      },
    ],
    'en',
  );

  assert.equal(reconciled.length, 1);
  assert.equal(
    reconciled[0]?.kind === 'tool' ? reconciled[0].item.status : '',
    'done',
  );
});
