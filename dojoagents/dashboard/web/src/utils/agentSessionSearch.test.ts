import assert from 'node:assert/strict';
import test from 'node:test';
import type { AgentSession } from '../types/agent.ts';
import { filterAgentSessionsByTitle } from './agentSessionSearch.ts';

const sessions = [
  {
    id: '1',
    title: 'Market Review',
    modelId: 'm',
    messages: [],
    createdAt: 1,
    updatedAt: 1,
  },
  {
    id: '2',
    title: '投资组合风险',
    modelId: 'm',
    messages: [],
    createdAt: 2,
    updatedAt: 2,
  },
] satisfies AgentSession[];

test('returns all sessions for an empty normalized query', () => {
  assert.deepEqual(filterAgentSessionsByTitle(sessions, '   '), sessions);
});

test('matches titles by case-insensitive substring without reordering', () => {
  assert.deepEqual(filterAgentSessionsByTitle(sessions, ' review '), [
    sessions[0],
  ]);
});

test('returns an empty list when no title matches', () => {
  assert.deepEqual(filterAgentSessionsByTitle(sessions, 'missing'), []);
});
