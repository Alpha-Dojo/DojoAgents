import assert from 'node:assert/strict';
import test from 'node:test';
import type { StockFinIndicatorRow } from '../types/entity.ts';
import {
  deaccumulateHkFinRows,
  dedupeFinRowsByComparableQuarter,
  isDisclosedFinRow,
  mapFinIndicatorsToFinancials,
  resolveNaturalMinusFiscalQuarters,
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

test('mapFinIndicatorsToFinancials keeps report_period_name quarters on the axis', () => {
  const financials = mapFinIndicatorsToFinancials(MISALIGNED_HK_ROWS, 'hk');

  assert.ok(financials.length >= 4);
  for (const point of financials) {
    assert.ok(point.revenue > 0, `${point.year} revenue should be positive, got ${point.revenue}`);
  }

  const byYear = Object.fromEntries(financials.map((row) => [row.year, row.revenue]));
  assert.equal(byYear['24Q2'], 236_503_000_000);
  assert.equal(byYear['24Q3'], 280_154_000_000);
  assert.equal(byYear['24Q4'], 236_454_000_000);
  assert.equal('25Q1' in byYear, true);
  assert.equal('26Q2' in byYear, false);
});

test('latest HK annual report keeps fiscal Q4 on axis; offset is title-only', () => {
  const latest = hkRow('2025年年报', '2025-12-31', '2026-03-31', 243_380_000_000, 25_541_000_000);
  assert.equal(unifiedFinPeriodAxisLabel(latest, 'hk'), '25Q4');
  assert.equal(resolveFiscalToNaturalOffset([latest]), 1);
  assert.equal(resolveNaturalMinusFiscalQuarters([latest]), 1);
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
  periodEndDate: string,
  revenue: number,
  publicDate?: string,
): StockFinIndicatorRow {
  return {
    symbol: 'BABA',
    report_period_name: reportPeriodName,
    std_report_date: stdReportDate,
    report_date: periodEndDate,
    public_date: publicDate ?? null,
    report_type: 'quarter',
    currency: 'USD',
    total_operating_revenue: revenue,
    net_profit_attr_parent: revenue * 0.1,
  };
}

test('BABA fiscal Q4 stays 25Q4 on axis; natural gap is title-only', () => {
  const row = usAdrRow('2025年第四季报', '2025-12-31', '2026-03-31', 34_330_000_000);
  assert.equal(unifiedFinPeriodAxisLabel(row, 'us'), '25Q4');
  assert.equal(resolveFiscalToNaturalOffset([row]), 1);
  assert.equal(resolveNaturalMinusFiscalQuarters([row]), 1);
});

test('misaligned calendar_period_label is ignored; axis uses report_period_name', () => {
  const row = hkRow('2024年三季报', '2024-09-30', '2024-12-31', 280_154_000_000, 49_127_000_000, {
    year: 2025,
    quarter: 1,
    label: '25Q1',
    index: 2025 * 4,
  });
  assert.equal(unifiedFinPeriodAxisLabel(row, 'hk'), '24Q3');
});

test('resolveFiscalToNaturalOffset detects -1 for AAPL-style period end before std', () => {
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
  assert.equal(resolveNaturalMinusFiscalQuarters(rows), -1);
  assert.equal(unifiedFinPeriodAxisLabel(rows[0], 'us'), '26Q2');
});

function usQuarterRow(
  symbol: string,
  reportPeriodName: string,
  stdReportDate: string,
  periodEndDate: string,
  revenue: number,
): StockFinIndicatorRow {
  return {
    symbol,
    report_period_name: reportPeriodName,
    std_report_date: stdReportDate,
    report_date: periodEndDate,
    report_type: 'quarter',
    total_operating_revenue: revenue,
    net_profit_attr_parent: revenue * 0.1,
  };
}

test('NVDA short period lag keeps natural-fiscal gap at 0', () => {
  const row = usQuarterRow('NVDA', '2026年一季报', '2026-03-31', '2026-04-26', 81_615_000_000);
  assert.equal(resolveFiscalToNaturalOffset([row]), 0);
  assert.equal(resolveNaturalMinusFiscalQuarters([row]), null);
  assert.equal(unifiedFinPeriodAxisLabel(row, 'us'), '26Q1');
});

test('May FYE ORCL/NKE floor(lag/90) is 1Q so latest 25Q4 + 1Q = 26Q1', () => {
  const orcl = usQuarterRow('ORCL', '2025年第四季报', '2025-12-31', '2026-05-31', 19_100_000_000);
  assert.equal(resolveNaturalMinusFiscalQuarters([orcl]), 1);
  assert.equal(unifiedFinPeriodAxisLabel(orcl, 'us'), '25Q4');

  const nke = usQuarterRow('NKE', '2025年第四季报', '2025-12-31', '2026-05-31', 10_000_000_000);
  assert.equal(resolveNaturalMinusFiscalQuarters([nke]), 1);
});

test('ADBE Apr-Jun period end before std maps latest fiscal Q2 with -1Q', () => {
  const rows: StockFinIndicatorRow[] = [
    usQuarterRow('ADBE', '2025年第四季报', '2025-12-31', '2025-11-28', 5_000_000_000),
    usQuarterRow('ADBE', '2026年一季报', '2026-03-31', '2026-02-27', 5_200_000_000),
    usQuarterRow('ADBE', '2026年第二季报', '2026-06-30', '2026-05-29', 5_400_000_000),
  ];
  // Series mode may be 0 (most Adobe quarters near calendar), but latest bar uses -1.
  assert.equal(resolveNaturalMinusFiscalQuarters(rows), -1);
  assert.equal(unifiedFinPeriodAxisLabel(rows[2], 'us'), '26Q2');
});

test('SNDK keeps fiscal quarters on axis while title can show natural gap', () => {
  const rows: StockFinIndicatorRow[] = [
    usQuarterRow('SNDK', '2024年第三季报', '2024-09-30', '2025-03-28', 1_695_000_000),
    usQuarterRow('SNDK', '2024年第四季报', '2024-12-31', '2025-06-27', 1_901_000_000),
    usQuarterRow('SNDK', '2025年一季报', '2025-03-31', '2025-10-03', 2_308_000_000),
    usQuarterRow('SNDK', '2025年第二季报', '2025-06-30', '2026-01-02', 3_025_000_000),
    usQuarterRow('SNDK', '2025年第三季报', '2025-09-30', '2026-04-03', 5_950_000_000),
  ];
  const offset = resolveFiscalToNaturalOffset(rows);
  assert.equal(offset, 2);
  assert.equal(resolveNaturalMinusFiscalQuarters(rows), 2);
  const latest = rows[rows.length - 1];
  assert.equal(unifiedFinPeriodAxisLabel(latest, 'us'), '25Q3');
  const financials = mapFinIndicatorsToFinancials(rows, 'us');
  const latestPoint = financials.at(-1);
  assert.ok(latestPoint);
  assert.equal(latestPoint?.year, '25Q3');
  assert.ok(
    latestPoint.revenueYoY != null && latestPoint.revenueYoY > 200,
    `expected strong fiscal Q3 YoY, got ${latestPoint.revenueYoY}`,
  );
});

test('mapFinIndicatorsToFinancials excludes undisclosed US ADR rows', () => {
  const rows: StockFinIndicatorRow[] = [
    usAdrRow('2024年第四季报', '2024-12-31', '2025-03-31', 33_600_000_000, '2025-03-31'),
    usAdrRow('2025年第四季报', '2025-12-31', '2099-03-31', 34_330_000_000, '2099-03-31'),
  ];

  const financials = mapFinIndicatorsToFinancials(rows, 'us');
  const labels = financials.map((row) => row.year);
  assert.ok(labels.includes('24Q4'));
  assert.equal(labels.includes('25Q4'), false);
  assert.equal(labels.includes('26Q1'), false);
});

test('isDisclosedFinRow uses disclosure report_date', () => {
  const disclosed = usAdrRow('2024年一季报', '2024-03-31', '2024-06-30', 34_000_000_000, '2024-06-30');
  const future = usAdrRow('2025年第四季报', '2025-12-31', '2099-03-31', 34_330_000_000, '2099-03-31');
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

/** Zhipu/MiniMax IPO shape: duplicate 年报 rows; one has garbage std_report_date. */
const IPO_HK_DUPLICATE_ANNUAL: StockFinIndicatorRow[] = [
  hkRow('2025年年报', '2022-12-31', '2025-12-31', 63_125_444, -157_650_323),
  hkRow('2023年年报', '2023-12-31', '2023-12-31', 136_938_747, -866_420_333),
  hkRow('2025年年报', '2025-12-31', '2025-12-31', 794_623_746, -5_154_119_051),
  hkRow('2025年中报', '2025-06-30', '2025-06-30', 205_669_956, -2_533_388_769),
  hkRow('2024年年报', '2024-12-31', '2024-12-31', 343_522_313, -3_250_880_652),
  hkRow('2024年中报', '2024-06-30', '2024-06-30', 49_380_769, -1_358_579_762),
  hkRow('2023年年报', '2023-12-31', '2023-12-31', 136_938_747, -866_420_333),
];

test('IPO HK duplicate annual rows keep a single 25Q4 with clean std date', () => {
  const deduped = dedupeFinRowsByComparableQuarter(IPO_HK_DUPLICATE_ANNUAL, 'hk');
  const q4_2025 = deduped.filter((row) => row.report_period_name === '2025年年报');
  assert.equal(q4_2025.length, 1);
  assert.equal(q4_2025[0].std_report_date, '2025-12-31');
  assert.equal(q4_2025[0].total_operating_revenue, 794_623_746);

  const financials = mapFinIndicatorsToFinancials(IPO_HK_DUPLICATE_ANNUAL, 'hk');
  const labels = financials.map((row) => row.year);
  assert.equal(labels.filter((label) => label === '25Q4').length, 1);
  assert.equal(new Set(labels).size, labels.length);

  const point = financials.find((row) => row.year === '25Q4');
  assert.ok(point);
  assert.equal(point?.revenue, 794_623_746);
  // Annual left cumulative (no Q3) still gets year-over-year vs prior annual.
  assert.ok(
    point.revenueYoY != null && point.revenueYoY > 100,
    `expected 25Q4 YoY vs 24Q4, got ${point.revenueYoY}`,
  );
});

test('HK annual + Q4 for same year keeps only one Q4 bar and prefers 第四季报', () => {
  const rows: StockFinIndicatorRow[] = [
    hkRow('2024年年报', '2024-12-31', '2025-03-31', 100_000_000, 10_000_000),
    {
      ...hkRow('2024年第四季报', '2024-12-31', '2025-03-31', 28_000_000, 3_000_000),
      report_type: 'quarter',
    },
  ];
  const deduped = dedupeFinRowsByComparableQuarter(rows, 'hk');
  assert.equal(deduped.length, 1);
  assert.equal(deduped[0].report_period_name, '2024年第四季报');
});

/** SpaceX IPO shape: crossed name/std/period-end with mirrored revenue pairs. */
const IPO_US_CROSS_LABELED: StockFinIndicatorRow[] = [
  usQuarterRow('SPCX', '2026年一季报', '2025-03-31', '2026-03-31', 4_067_000_000),
  usQuarterRow('SPCX', '2025年一季报', '2026-03-31', '2025-03-31', 4_694_000_000),
  usQuarterRow('SPCX', '2026年一季报', '2026-03-31', '2026-03-31', 4_694_000_000),
  usQuarterRow('SPCX', '2025年一季报', '2025-03-31', '2025-03-31', 4_067_000_000),
];

test('IPO US cross-labeled quarters collapse to consistent 25Q1 and 26Q1', () => {
  const deduped = dedupeFinRowsByComparableQuarter(IPO_US_CROSS_LABELED, 'us');
  assert.equal(deduped.length, 2);

  const byName = Object.fromEntries(
    deduped.map((row) => [row.report_period_name, row.total_operating_revenue]),
  );
  assert.equal(byName['2025年一季报'], 4_067_000_000);
  assert.equal(byName['2026年一季报'], 4_694_000_000);

  const financials = mapFinIndicatorsToFinancials(IPO_US_CROSS_LABELED, 'us');
  assert.deepEqual(
    financials.map((row) => row.year),
    ['25Q1', '26Q1'],
  );
  assert.equal(financials[0].revenue, 4_067_000_000);
  assert.equal(financials[1].revenue, 4_694_000_000);
  assert.ok(financials[1].revenueYoY != null && financials[1].revenueYoY > 0);
});
