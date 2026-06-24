import { describe, expect, it } from 'vitest';
import { windowReturnFromIndexSeries } from '../api/adapters/transforms';

describe('windowReturnFromIndexSeries', () => {
  const series = [
    { date: '2025-01-01', value: 100 },
    { date: '2025-01-02', value: 101 },
    { date: '2025-01-03', value: 102 },
    { date: '2025-01-06', value: 103 },
    { date: '2025-01-07', value: 104 },
    { date: '2025-01-08', value: 105 },
  ];

  it('returns cumulative move when days is 0', () => {
    expect(windowReturnFromIndexSeries(series, 0)).toBe(5);
  });

  it('returns window move over N trading sessions', () => {
    expect(windowReturnFromIndexSeries(series, 5)).toBeCloseTo(4.762, 2);
  });
});
