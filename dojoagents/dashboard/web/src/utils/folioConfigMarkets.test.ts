import assert from 'node:assert/strict';
import test from 'node:test';
import { FOLIO_MARKETS } from '../types/folio.ts';
import { resolveFolioConfigMarkets, resolveFolioSnapshotMarkets } from './folioConfigMarkets.ts';

test('shows only markets present in the selected portfolio content', () => {
  const markets = resolveFolioConfigMarkets({
    positions: [
      { market: 'hk' },
      { market: 'cn' },
      { market: 'hk' },
    ],
    candidates: [
      { market: 'us' },
    ],
  });

  assert.deepEqual(markets, ['us', 'cn', 'hk']);
});

test('falls back to every market when the portfolio has no market data', () => {
  const markets = resolveFolioConfigMarkets({
    positions: [],
    candidates: [],
  });

  assert.deepEqual(markets, FOLIO_MARKETS);
});

test('shows only markets with candidates or holdings in portfolio snapshots', () => {
  const markets = resolveFolioSnapshotMarkets({
    us: { candidateCount: 0, holdingCount: 0 },
    cn: { candidateCount: 2, holdingCount: 0 },
    hk: { candidateCount: 0, holdingCount: 1 },
  });

  assert.deepEqual(markets, ['cn', 'hk']);
});

test('falls back to every market when snapshots have no portfolio content', () => {
  const markets = resolveFolioSnapshotMarkets({
    us: { candidateCount: 0, holdingCount: 0 },
    cn: { candidateCount: 0, holdingCount: 0 },
    hk: { candidateCount: 0, holdingCount: 0 },
  });

  assert.deepEqual(markets, FOLIO_MARKETS);
});
