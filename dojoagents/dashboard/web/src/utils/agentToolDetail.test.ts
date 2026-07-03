import assert from 'node:assert/strict';
import test from 'node:test';
import { formatToolResultData } from './agentToolDetail.ts';

test('formatToolResultData discloses default 10% buy sizing in zh', () => {
  const summary = formatToolResultData(
    {
      id: 'p1',
      order_result: {
        ticker: 'AAPL',
        order_side: 'buy',
        qty: 1018,
        resolution: { qty_source: 'default_10pct' },
      },
    },
    'zh',
  );

  assert.match(summary ?? '', /未指定买入数量/);
  assert.match(summary ?? '', /10%/);
  assert.match(summary ?? '', /AAPL/);
  assert.match(summary ?? '', /1,018 股/);
});

test('formatToolResultData discloses default 10% buy sizing in en', () => {
  const summary = formatToolResultData(
    {
      order_result: {
        ticker: 'AAPL',
        order_side: 'buy',
        qty: 1018,
        resolution: { qty_source: 'default_10pct' },
      },
    },
    'en',
  );

  assert.match(summary ?? '', /Buy quantity not specified/);
  assert.match(summary ?? '', /10% of available cash/);
  assert.match(summary ?? '', /AAPL · 1,018 shares/);
});

test('formatToolResultData skips disclosure when qty was user-specified', () => {
  const summary = formatToolResultData(
    {
      order_result: {
        ticker: 'AAPL',
        order_side: 'buy',
        qty: 100,
        resolution: { qty_source: 'user' },
      },
    },
    'zh',
  );

  assert.equal(summary, null);
});

test('formatToolResultData discloses batch filled orders with default sizing', () => {
  const summary = formatToolResultData(
    {
      order_result: {
        filled_orders: [
          {
            ticker: 'AAPL',
            order_side: 'buy',
            qty: 1018,
            resolution: { qty_source: 'default_10pct' },
          },
          {
            ticker: 'MSFT',
            order_side: 'buy',
            qty: 200,
            resolution: { qty_source: 'user' },
          },
        ],
      },
    },
    'zh',
  );

  assert.match(summary ?? '', /AAPL/);
  assert.doesNotMatch(summary ?? '', /MSFT/);
});
