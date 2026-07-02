import assert from 'node:assert/strict';
import test from 'node:test';
import type { AgentActivityStep } from '../types/agent.ts';
import { stripRenderedChartBlocksFromSteps } from './agentVizContent.ts';

test('strips chart JSON from text steps without changing chronological order', () => {
  const steps: AgentActivityStep[] = [
    { kind: 'text', id: 'text-1', text: '准备数据。' },
    {
      kind: 'tool',
      id: 'tool-1',
      item: { tool: 'chart', status: 'done' },
    },
    {
      kind: 'text',
      id: 'text-2',
      text: '结果如下。\n```DOJO_CHART\n{"type":"line","data":[]}\n```',
    },
  ];

  const stripped = stripRenderedChartBlocksFromSteps(steps, true);

  assert.deepEqual(
    stripped.map((step) => step.kind),
    ['text', 'tool', 'text'],
  );
  assert.equal(stripped[0], steps[0]);
  assert.equal(
    stripped[2]?.kind === 'text' ? stripped[2].text : '',
    '结果如下。',
  );
});
