import { useMemo, useState } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import type { EntityIncomeDistributionSlice, EntityIncomeMainopType } from '../../types/entity';
import { formatFinancialAmount } from '../../utils/entityCharts';
import {
  buildDonutPaths,
  formatReportDateLabel,
  INCOME_MAINOP_TYPES,
  prepareIncomeChartSlices,
  prepareIncomeListRows,
  type IncomeChartSlice,
} from '../../utils/entityIncomeDistribution';
import { LoadingIndicator } from '../ui/LoadingIndicator';
import { EntityCard } from './EntityCard';

interface EntityIncomeDistributionPanelProps {
  distributions: EntityIncomeDistributionSlice[];
  reportDate: string | null;
  loading?: boolean;
}

const DONUT_CX = 50;
const DONUT_CY = 50;
const DONUT_OUTER_R = 46;
const DONUT_INNER_R = 32;

const EMPTY_MESSAGE_KEYS: Record<
  EntityIncomeMainopType,
  'entityPage.incomeEmptyIndustry' | 'entityPage.incomeEmptyProduct' | 'entityPage.incomeEmptyRegion'
> = {
  '1': 'entityPage.incomeEmptyIndustry',
  '2': 'entityPage.incomeEmptyProduct',
  '3': 'entityPage.incomeEmptyRegion',
};

const TITLE_KEYS: Record<
  EntityIncomeMainopType,
  'entityPage.incomeByIndustry' | 'entityPage.incomeByProduct' | 'entityPage.incomeByRegion'
> = {
  '1': 'entityPage.incomeByIndustry',
  '2': 'entityPage.incomeByProduct',
  '3': 'entityPage.incomeByRegion',
};

interface IncomeDonutChartProps {
  mainopType: EntityIncomeMainopType;
  items: EntityIncomeDistributionSlice['items'];
}

function IncomeDonutChart({ mainopType, items }: IncomeDonutChartProps) {
  const { t, locale } = useTranslation();
  const [hoveredKey, setHoveredKey] = useState<string | null>(null);

  const slices = useMemo(
    () => prepareIncomeChartSlices(items, t('entityPage.incomeOthers')),
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
    <section className="entity-income__chart" aria-label={t(TITLE_KEYS[mainopType])}>
      <h4 className="entity-income__chart-title">{t(TITLE_KEYS[mainopType])}</h4>

      {!slices.length ? (
        <p className="entity-income__chart-empty">{t(EMPTY_MESSAGE_KEYS[mainopType])}</p>
      ) : (
        <div className="entity-income__chart-body">
          <div className="entity-income__donut-wrap">
            <svg viewBox="0 0 100 100" className="entity-income__donut" role="img">
              {paths.map((segment) => {
                const isActive = !activeDonutKey || activeDonutKey === segment.key;
                return (
                  <path
                    key={segment.key}
                    d={segment.path}
                    fill={segment.color}
                    className={`entity-income__donut-segment${isActive ? '' : ' entity-income__donut-segment--dim'}${
                      activeDonutKey === segment.key ? ' entity-income__donut-segment--active' : ''
                    }`}
                    onMouseEnter={() => setHoveredKey(segment.key)}
                    onMouseLeave={() => setHoveredKey(null)}
                  />
                );
              })}
            </svg>
            <div className="entity-income__donut-center" aria-hidden>
              <span className="entity-income__donut-center-total">
                {formatFinancialAmount(totalValue, locale)}
              </span>
            </div>
          </div>

          {activeSlice ? (
            <p
              className="entity-income__detail-line"
              title={`${activeSlice.name} ${formatFinancialAmount(activeSlice.value, locale)} ${(activeSlice.ratio * 100).toFixed(1)}%`}
            >
              <span
                className="entity-income__detail-dot"
                style={{ backgroundColor: activeSlice.color }}
                aria-hidden
              />
              <span className="entity-income__detail-name">{activeSlice.name}</span>
              <span className="entity-income__detail-metrics">
                <span className="entity-income__detail-amount">
                  {formatFinancialAmount(activeSlice.value, locale)}
                </span>
                <span className="entity-income__detail-ratio">
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

export function EntityIncomeDistributionPanel({
  distributions,
  reportDate,
  loading = false,
}: EntityIncomeDistributionPanelProps) {
  const { t } = useTranslation();

  const distributionByType = useMemo(() => {
    const map = new Map<EntityIncomeMainopType, EntityIncomeDistributionSlice['items']>();
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
    <EntityCard
      title={t('entityPage.incomeDistributionTitle')}
      className="entity-card--income-distribution"
      actions={
        reportDateLabel ? (
          <span className="entity-income__as-of">{t('entityPage.incomeAsOf', { date: reportDateLabel })}</span>
        ) : null
      }
    >
      {loading && !distributions.length ? (
        <LoadingIndicator
          className="entity-chart-stage__status"
          label={t('entityPage.incomeLoading')}
          variant="panel"
        />
      ) : (
        <div className="entity-income">
          {INCOME_MAINOP_TYPES.map((mainopType) => (
            <IncomeDonutChart
              key={mainopType}
              mainopType={mainopType}
              items={distributionByType.get(mainopType) ?? []}
            />
          ))}
        </div>
      )}
    </EntityCard>
  );
}
