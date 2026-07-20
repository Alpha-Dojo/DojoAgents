import assert from 'node:assert/strict';
import test from 'node:test';
import type { EntityKlineBar, StockFinIndicatorRow } from '../types/entity.ts';
import { buildEntityKeyMetrics } from './entityKeyMetrics.ts';

function metricValue(
  rows: ReturnType<typeof buildEntityKeyMetrics>,
  labelKey: string,
): string {
  for (const row of rows) {
    const hit = row.find((m) => m.labelKey === labelKey);
    if (hit) return hit.value;
  }
  throw new Error(`metric ${labelKey} not found`);
}

const staleFin: StockFinIndicatorRow = {
  symbol: '2513.HK',
  report_period_name: '2025年年报',
  std_report_date: '2025-12-31',
  report_date: '2026-03-31',
  report_type: 'accumulate',
  total_market_cap: 802_000_000_000,
  hksk_market_cap: 802_000_000_000,
  net_profit_attr_parent: -10_000_000_000,
};

const bars: EntityKlineBar[] = [
  {
    date: '2026-07-17',
    open: 1360,
    high: 1400,
    low: 1100,
    close: 1107,
    volume: 14_600_000,
    amount: 0,
  },
];

test('market cap prefers quote.market_cap over stale fin total_market_cap', () => {
  const rows = buildEntityKeyMetrics({
    finRows: [staleFin],
    klineBars: bars,
    market: 'hk',
    quoteDetail: {
      market_cap: 515_862_000_000,
      total_shares: 466_000_000,
    },
  });
  assert.equal(metricValue(rows, 'marketCap'), '516B');
});

test('market cap falls back to total_shares × lastClose when quote.market_cap missing', () => {
  const rows = buildEntityKeyMetrics({
    finRows: [staleFin],
    klineBars: bars,
    market: 'hk',
    quoteDetail: {
      market_cap: null,
      total_shares: 466_000_000,
    },
  });
  assert.equal(metricValue(rows, 'marketCap'), '516B');
});

test('market cap ignores fin total_market_cap when quote fields are absent', () => {
  const rows = buildEntityKeyMetrics({
    finRows: [staleFin],
    klineBars: bars,
    market: 'hk',
    quoteDetail: null,
  });
  assert.equal(metricValue(rows, 'marketCap'), '—');
});

test('ttm pe uses live market cap rather than stale fin market cap', () => {
  const finRows: StockFinIndicatorRow[] = [
    {
      symbol: '2513.HK',
      report_period_name: '2025年一季报',
      std_report_date: '2025-03-31',
      report_date: '2025-03-31',
      report_type: 'single',
      total_market_cap: 802_000_000_000,
      net_profit_attr_parent: 5_000_000_000,
    },
    {
      symbol: '2513.HK',
      report_period_name: '2025年中报',
      std_report_date: '2025-06-30',
      report_date: '2025-06-30',
      report_type: 'single',
      total_market_cap: 802_000_000_000,
      net_profit_attr_parent: 5_000_000_000,
    },
    {
      symbol: '2513.HK',
      report_period_name: '2025年三季报',
      std_report_date: '2025-09-30',
      report_date: '2025-09-30',
      report_type: 'single',
      total_market_cap: 802_000_000_000,
      net_profit_attr_parent: 5_000_000_000,
    },
    {
      symbol: '2513.HK',
      report_period_name: '2025年年报',
      std_report_date: '2025-12-31',
      report_date: '2025-12-31',
      report_type: 'single',
      total_market_cap: 802_000_000_000,
      net_profit_attr_parent: 5_000_000_000,
    },
  ];
  const liveCap = 515_862_000_000;
  const rows = buildEntityKeyMetrics({
    finRows,
    klineBars: bars,
    market: 'us',
    quoteDetail: {
      market_cap: liveCap,
      total_shares: 466_000_000,
    },
  });
  // 515.862B / 20B ≈ 25.793 → formatPeDisplay → "25.8"
  assert.equal(metricValue(rows, 'peTtm'), '25.8');
});
