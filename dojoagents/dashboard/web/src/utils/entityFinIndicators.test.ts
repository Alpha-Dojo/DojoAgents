import assert from 'node:assert/strict';
import test from 'node:test';
import type { StockFinIndicatorRow } from '../types/entity.ts';
import {
  deaccumulateHkFinRows,
  isDisclosedFinRow,
  mapFinIndicatorsToFinancials,
  resolveFiscalToNaturalOffset,
  resolveHkPeriodFinRow,
  unifiedFinPeriodAxisLabel,
} from './entityFinIndicators.ts';

function hkRow(
  reportPeriodName: string,
  stdReportDate: string,
  reportDate: string,
  revenue: number,
  netProfit: number,
  calendar?: {
    year: number;
    quarter: number;
    label: string;
    index: number;
  },
): StockFinIndicatorRow {
  return {
    symbol: '9988.HK',
    report_period_name: reportPeriodName,
    std_report_date: stdReportDate,
    report_date: reportDate,
    report_type: 'accumulate',
    total_operating_revenue: revenue,
    net_profit_attr_parent: netProfit,
    calendar_year: calendar?.year ?? null,
    calendar_quarter: calendar?.quarter ?? null,
    calendar_period_label: calendar?.label ?? null,
    calendar_period_index: calendar?.index ?? null,
  };
}

/** Alibaba-like HK rows with misaligned calendar_* (+2 quarter shift). */
const MISALIGNED_HK_ROWS: StockFinIndicatorRow[] = [
  hkRow('2023年三季报', '2023-09-30', '2023-12-31', 719_294_000_000, 76_644_000_000, {
    year: 2024,
    quarter: 1,
    label: '24Q1',
    index: 2024 * 4,
  }),
  hkRow('2023年年报', '2023-12-31', '2024-03-31', 941_168_000_000, 80_009_000_000, {
    year: 2024,
    quarter: 2,
    label: '24Q2',
    index: 2024 * 4 + 1,
  }),
  hkRow('2024年一季报', '2024-03-31', '2024-06-30', 243_236_000_000, 24_390_000_000, {
    year: 2024,
    quarter: 3,
    label: '24Q3',
    index: 2024 * 4 + 2,
  }),
  hkRow('2024年中报', '2024-06-30', '2024-09-30', 479_739_000_000, 68_423_000_000, {
    year: 2024,
    quarter: 4,
    label: '24Q4',
    index: 2024 * 4 + 3,
  }),
  hkRow('2024年三季报', '2024-09-30', '2024-12-31', 759_893_000_000, 117_550_000_000, {
    year: 2025,
    quarter: 1,
    label: '25Q1',
    index: 2025 * 4,
  }),
  hkRow('2024年年报', '2024-12-31', '2025-03-31', 996_347_000_000, 130_109_000_000, {
    year: 2025,
    quarter: 2,
    label: '25Q2',
    index: 2025 * 4 + 1,
  }),
  hkRow('2025年一季报', '2025-03-31', '2025-06-30', 247_652_000_000, 40_649_000_000, {
    year: 2025,
    quarter: 3,
    label: '25Q3',
    index: 2025 * 4 + 2,
  }),
  hkRow('2025年中报', '2025-06-30', '2025-09-30', 495_447_000_000, 61_668_000_000, {
    year: 2025,
    quarter: 4,
    label: '25Q4',
    index: 2025 * 4 + 3,
  }),
];

test('deaccumulateHkFinRows uses report_period_name even when calendar_* is offset', () => {
  const rows = deaccumulateHkFinRows(MISALIGNED_HK_ROWS);
  const byName = Object.fromEntries(
    rows.map((row) => [row.report_period_name, row.total_operating_revenue]),
  );

  assert.equal(byName['2023年年报'], 221_874_000_000);
  assert.equal(byName['2024年中报'], 236_503_000_000);
  assert.equal(byName['2024年三季报'], 280_154_000_000);
  assert.equal(byName['2024年年报'], 236_454_000_000);
  assert.equal(byName['2025年中报'], 247_795_000_000);

  for (const revenue of Object.values(byName)) {
    assert.ok(revenue != null && revenue > 0, `expected positive revenue, got ${revenue}`);
  }
});

test('mapFinIndicatorsToFinancials maps natural calendar from disclosure date', () => {
  const financials = mapFinIndicatorsToFinancials(MISALIGNED_HK_ROWS, 'hk');

  assert.ok(financials.length >= 4);
  for (const point of financials) {
    assert.ok(point.revenue > 0, `${point.year} revenue should be positive, got ${point.revenue}`);
  }

  const byYear = Object.fromEntries(financials.map((row) => [row.year, row.revenue]));
  assert.equal(byYear['24Q3'], 236_503_000_000);
  assert.equal(byYear['24Q4'], 280_154_000_000);
  assert.equal(byYear['25Q1'], 236_454_000_000);
  assert.equal('26Q2' in byYear, false);
});

test('latest HK annual report maps to 26Q1 via disclosure quarter', () => {
  const latest = hkRow('2025年年报', '2025-12-31', '2026-03-31', 243_380_000_000, 25_541_000_000);
  assert.equal(unifiedFinPeriodAxisLabel(latest, 'hk'), '26Q1');
  assert.equal(resolveFiscalToNaturalOffset([latest]), 1);
});

test('resolveHkPeriodFinRow differences eps using report_period_name', () => {
  const rows: StockFinIndicatorRow[] = [
    {
      ...hkRow('2024年一季报', '2024-03-31', '2024-06-30', 243_236_000_000, 24_390_000_000),
      eps_basic: 1.0,
      roe_weighted: 4.0,
      roa: 1.0,
    },
    {
      ...hkRow('2024年中报', '2024-06-30', '2024-09-30', 479_739_000_000, 68_423_000_000, {
        year: 2024,
        quarter: 4,
        label: '24Q4',
        index: 2024 * 4 + 3,
      }),
      eps_basic: 3.0,
      roe_weighted: 8.0,
      roa: 2.5,
    },
  ];

  const resolved = resolveHkPeriodFinRow(rows, 'hk');
  assert.ok(resolved);
  assert.equal(resolved?.eps_basic, 2.0);
  assert.equal(resolved?.roe_weighted, 4.0);
  assert.equal(resolved?.roa, 1.5);
});

function usAdrRow(
  reportPeriodName: string,
  stdReportDate: string,
  reportDate: string,
  revenue: number,
): StockFinIndicatorRow {
  return {
    symbol: 'BABA',
    report_period_name: reportPeriodName,
    std_report_date: stdReportDate,
    report_date: reportDate,
    report_type: 'quarter',
    currency: 'USD',
    total_operating_revenue: revenue,
    net_profit_attr_parent: revenue * 0.1,
  };
}

test('BABA latest fiscal Q4 maps to natural 26Q1 from March disclosure', () => {
  const row = usAdrRow('2025年第四季报', '2025-12-31', '2026-03-31', 34_330_000_000);
  assert.equal(unifiedFinPeriodAxisLabel(row, 'us'), '26Q1');
  assert.equal(resolveFiscalToNaturalOffset([row]), 1);
});

test('misaligned calendar_period_label is ignored; axis uses disclosure quarter', () => {
  const row = hkRow('2024年三季报', '2024-09-30', '2024-12-31', 280_154_000_000, 49_127_000_000, {
    year: 2025,
    quarter: 1,
    label: '25Q1',
    index: 2025 * 4,
  });
  assert.equal(unifiedFinPeriodAxisLabel(row, 'hk'), '24Q4');
});

test('resolveFiscalToNaturalOffset detects -1 for AAPL-style pre-period disclosure', () => {
  const rows: StockFinIndicatorRow[] = [
    {
      symbol: 'AAPL',
      report_period_name: '2026年第二季报',
      std_report_date: '2026-06-30',
      report_date: '2026-03-28',
      report_type: 'quarter',
    },
    {
      symbol: 'AAPL',
      report_period_name: '2025年第四季报',
      std_report_date: '2025-12-31',
      report_date: '2025-09-27',
      report_type: 'quarter',
    },
  ];
  assert.equal(resolveFiscalToNaturalOffset(rows), -1);
  assert.equal(unifiedFinPeriodAxisLabel(rows[0], 'us', resolveFiscalToNaturalOffset(rows)), '26Q1');
});

function usQuarterRow(
  symbol: string,
  reportPeriodName: string,
  stdReportDate: string,
  reportDate: string,
  revenue: number,
): StockFinIndicatorRow {
  return {
    symbol,
    report_period_name: reportPeriodName,
    std_report_date: stdReportDate,
    report_date: reportDate,
    report_type: 'quarter',
    total_operating_revenue: revenue,
    net_profit_attr_parent: revenue * 0.1,
  };
}

test('NVDA short post-period disclosure keeps fiscal quarter on natural calendar axis', () => {
  const row = usQuarterRow('NVDA', '2026年一季报', '2026-03-31', '2026-04-26', 81_615_000_000);
  assert.equal(resolveFiscalToNaturalOffset([row]), 0);
  assert.equal(unifiedFinPeriodAxisLabel(row, 'us', 0), '26Q1');
});

test('SNDK long disclosure lag maps latest fiscal Q3 to natural 26Q1', () => {
  const rows: StockFinIndicatorRow[] = [
    usQuarterRow('SNDK', '2024年第三季报', '2024-09-30', '2025-03-28', 1_695_000_000),
    usQuarterRow('SNDK', '2024年第四季报', '2024-12-31', '2025-06-27', 1_901_000_000),
    usQuarterRow('SNDK', '2025年一季报', '2025-03-31', '2025-10-03', 2_308_000_000),
    usQuarterRow('SNDK', '2025年第二季报', '2025-06-30', '2026-01-02', 3_025_000_000),
    usQuarterRow('SNDK', '2025年第三季报', '2025-09-30', '2026-04-03', 5_950_000_000),
  ];
  const offset = resolveFiscalToNaturalOffset(rows);
  assert.equal(offset, 2);
  const latest = rows[rows.length - 1];
  assert.equal(unifiedFinPeriodAxisLabel(latest, 'us', offset), '26Q1');
  const financials = mapFinIndicatorsToFinancials(rows, 'us');
  const latestPoint = financials.at(-1);
  assert.ok(latestPoint);
  assert.equal(latestPoint?.year, '26Q1');
  assert.ok(
    latestPoint.revenueYoY != null && latestPoint.revenueYoY > 200,
    `expected strong 26Q1 YoY, got ${latestPoint.revenueYoY}`,
  );
});

test('mapFinIndicatorsToFinancials excludes undisclosed US ADR rows', () => {
  const rows: StockFinIndicatorRow[] = [
    usAdrRow('2024年第四季报', '2024-12-31', '2025-03-31', 33_600_000_000),
    usAdrRow('2025年第四季报', '2025-12-31', '2099-03-31', 34_330_000_000),
  ];

  const financials = mapFinIndicatorsToFinancials(rows, 'us');
  const labels = financials.map((row) => row.year);
  assert.ok(labels.includes('25Q1'));
  assert.equal(labels.includes('26Q1'), false);
  assert.equal(labels.includes('26Q2'), false);
});

test('isDisclosedFinRow uses disclosure report_date', () => {
  const disclosed = usAdrRow('2024年一季报', '2024-03-31', '2024-06-30', 34_000_000_000);
  const future = usAdrRow('2025年第四季报', '2025-12-31', '2099-03-31', 34_330_000_000);
  assert.equal(isDisclosedFinRow(disclosed), true);
  assert.equal(isDisclosedFinRow(future), false);
});

/** Real 9988.HK API shape: oldest row is 2022 annual cumulative without 2022 Q3. */
const HK_INCOMPLETE_2022_BASELINE: StockFinIndicatorRow[] = [
  hkRow('2022年年报', '2022-12-31', '2023-03-31', 868_690_000_000, 72_000_000_000),
  hkRow('2023年一季报', '2023-03-31', '2023-06-30', 234_156_000_000, 33_000_000_000),
  hkRow('2023年中报', '2023-06-30', '2023-09-30', 458_046_000_000, 59_000_000_000),
  hkRow('2023年三季报', '2023-09-30', '2023-12-31', 719_294_000_000, 76_644_000_000),
  hkRow('2023年年报', '2023-12-31', '2024-03-31', 941_168_000_000, 80_009_000_000),
  hkRow('2024年一季报', '2024-03-31', '2024-06-30', 243_236_000_000, 24_390_000_000),
  hkRow('2024年中报', '2024-06-30', '2024-09-30', 479_739_000_000, 68_423_000_000),
  hkRow('2024年三季报', '2024-09-30', '2024-12-31', 759_893_000_000, 117_550_000_000),
  hkRow('2024年年报', '2024-12-31', '2025-03-31', 996_347_000_000, 130_109_000_000),
];

test('HK 24Q1 YoY stays positive when 2022 Q3 is missing from API history', () => {
  const financials = mapFinIndicatorsToFinancials(HK_INCOMPLETE_2022_BASELINE, 'hk');
  const q1 = financials.find((row) => row.year === '24Q1');
  assert.ok(q1, 'expected 24Q1 chart point');
  assert.ok(
    q1.revenueYoY != null && q1.revenueYoY > 0 && q1.revenueYoY < 20,
    `expected modest positive YoY, got ${q1.revenueYoY}`,
  );
  assert.notEqual(q1.revenueYoY, -74.5);
});

test('deaccumulateHkFinRows estimates 2022 annual single quarter when Q3 is absent', () => {
  const rows = deaccumulateHkFinRows(HK_INCOMPLETE_2022_BASELINE);
  const annual2022 = rows.find((row) => row.report_period_name === '2022年年报');
  assert.ok(annual2022);
  const rev = annual2022.total_operating_revenue ?? 0;
  assert.ok(rev > 180_000_000_000 && rev < 250_000_000_000, `expected ~single Q4, got ${rev}`);
  assert.notEqual(rev, 868_690_000_000);
});
