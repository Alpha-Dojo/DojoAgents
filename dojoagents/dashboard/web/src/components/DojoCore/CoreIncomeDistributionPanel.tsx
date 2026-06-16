import { useMemo, useState } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import type { CoreIncomeDistributionSlice, CoreIncomeMainopType } from '../../types/dojoCore';
import { formatFinancialAmount } from '../../utils/coreCharts';
import {
  buildDonutPaths,
  formatReportDateLabel,
  INCOME_MAINOP_TYPES,
  prepareIncomeChartSlices,
  prepareIncomeListRows,
  type IncomeChartSlice,
} from '../../utils/coreIncomeDistribution';
import { CoreCard } from './CoreCard';

interface CoreIncomeDistributionPanelProps {
  distributions: CoreIncomeDistributionSlice[];
  reportDate: string | null;
  loading?: boolean;
}

const DONUT_CX = 50;
const DONUT_CY = 50;
const DONUT_OUTER_R = 46;
const DONUT_INNER_R = 32;

const EMPTY_MESSAGE_KEYS: Record<
  CoreIncomeMainopType,
  'core.incomeEmptyIndustry' | 'core.incomeEmptyProduct' | 'core.incomeEmptyRegion'
> = {
  '1': 'core.incomeEmptyIndustry',
  '2': 'core.incomeEmptyProduct',
  '3': 'core.incomeEmptyRegion',
};

const TITLE_KEYS: Record<
  CoreIncomeMainopType,
  'core.incomeByIndustry' | 'core.incomeByProduct' | 'core.incomeByRegion'
> = {
  '1': 'core.incomeByIndustry',
  '2': 'core.incomeByProduct',
  '3': 'core.incomeByRegion',
};

interface IncomeDonutChartProps {
  mainopType: CoreIncomeMainopType;
  items: CoreIncomeDistributionSlice['items'];
}

function IncomeDonutChart({ mainopType, items }: IncomeDonutChartProps) {
  const { t, locale } = useTranslation();
  const [hoveredKey, setHoveredKey] = useState<string | null>(null);

  const slices = useMemo(
    () => prepareIncomeChartSlices(items, t('core.incomeOthers')),
    [items, t],
  );

  const paths = useMemo(
    () => buildDonutPaths(slices, DONUT_CX, DONUT_CY, DONUT_OUTER_R, DONUT_INNER_R),
    [slices],
  );

  const totalValue = useMemo(
    () => prepareIncomeListRows(items).reduce((sum, row) => sum + row.value, 0),
    [items],
  );

  const activeDonutKey = hoveredKey ?? slices[0]?.key ?? null;

  const activeSlice = useMemo((): IncomeChartSlice | null => {
    if (!slices.length) return null;
    if (!activeDonutKey) return slices[0];
    return slices.find((slice) => slice.key === activeDonutKey) ?? slices[0];
  }, [activeDonutKey, slices]);

  return (
    <section className="core-income__chart" aria-label={t(TITLE_KEYS[mainopType])}>
      <h4 className="core-income__chart-title">{t(TITLE_KEYS[mainopType])}</h4>

      {!slices.length ? (
        <p className="core-income__chart-empty">{t(EMPTY_MESSAGE_KEYS[mainopType])}</p>
      ) : (
        <div className="core-income__chart-body">
          <div className="core-income__donut-wrap">
            <svg viewBox="0 0 100 100" className="core-income__donut" role="img">
              {paths.map((segment) => {
                const isActive = !activeDonutKey || activeDonutKey === segment.key;
                return (
                  <path
                    key={segment.key}
                    d={segment.path}
                    fill={segment.color}
                    className={`core-income__donut-segment${isActive ? '' : ' core-income__donut-segment--dim'}${
                      activeDonutKey === segment.key ? ' core-income__donut-segment--active' : ''
                    }`}
                    onMouseEnter={() => setHoveredKey(segment.key)}
                    onMouseLeave={() => setHoveredKey(null)}
                  />
                );
              })}
            </svg>
            <div className="core-income__donut-center" aria-hidden>
              <span className="core-income__donut-center-total">
                {formatFinancialAmount(totalValue, locale)}
              </span>
            </div>
          </div>

          {activeSlice ? (
            <p
              className="core-income__detail-line"
              title={`${activeSlice.name} ${formatFinancialAmount(activeSlice.value, locale)} ${(activeSlice.ratio * 100).toFixed(1)}%`}
            >
              <span
                className="core-income__detail-dot"
                style={{ backgroundColor: activeSlice.color }}
                aria-hidden
              />
              <span className="core-income__detail-name">{activeSlice.name}</span>
              <span className="core-income__detail-metrics">
                <span className="core-income__detail-amount">
                  {formatFinancialAmount(activeSlice.value, locale)}
                </span>
                <span className="core-income__detail-ratio">
                  {(activeSlice.ratio * 100).toFixed(1)}%
                </span>
              </span>
            </p>
          ) : null}
        </div>
      )}
    </section>
  );
}

export function CoreIncomeDistributionPanel({
  distributions,
  reportDate,
  loading = false,
}: CoreIncomeDistributionPanelProps) {
  const { t } = useTranslation();

  const distributionByType = useMemo(() => {
    const map = new Map<CoreIncomeMainopType, CoreIncomeDistributionSlice['items']>();
    for (const mainopType of INCOME_MAINOP_TYPES) {
      map.set(mainopType, []);
    }
    for (const slice of distributions) {
      map.set(slice.mainop_type, slice.items);
    }
    return map;
  }, [distributions]);

  const reportDateLabel = formatReportDateLabel(reportDate);

  return (
    <CoreCard
      title={t('core.incomeDistributionTitle')}
      className="core-card--income-distribution"
      actions={
        reportDateLabel ? (
          <span className="core-income__as-of">{t('core.incomeAsOf', { date: reportDateLabel })}</span>
        ) : null
      }
    >
      {loading && !distributions.length ? (
        <p className="core-chart-stage__status">{t('core.incomeLoading')}</p>
      ) : (
        <div className="core-income">
          {INCOME_MAINOP_TYPES.map((mainopType) => (
            <IncomeDonutChart
              key={mainopType}
              mainopType={mainopType}
              items={distributionByType.get(mainopType) ?? []}
            />
          ))}
        </div>
      )}
    </CoreCard>
  );
}
