import { useMemo } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import type { EntityFinancialYear } from '../../types/entity';
import type { MarketCode } from '../../types/market';
import {
  chartY,
  formatFinancialAmount,
  formatSignedPercent,
} from '../../utils/entityCharts';
import { MARKET_LEGAL_CURRENCY_KEY } from '../../utils/marketDisplay';
import { LoadingIndicator } from '../ui/LoadingIndicator';
import { EntityCard } from './EntityCard';

interface EntityRevenueChartProps {
  financials: EntityFinancialYear[];
  loading?: boolean;
  market?: MarketCode | null;
}

const YOY_W = 520;
const YOY_H = 52;
const YOY_PAD_X = 18;
const YOY_PAD_Y = 10;

function columnCenterPct(index: number, count: number): number {
  if (count <= 0) return 50;
  return ((index + 0.5) / count) * 100;
}

function yoyX(index: number, count: number): number {
  if (count <= 1) return YOY_PAD_X;
  return YOY_PAD_X + (index / (count - 1)) * (YOY_W - YOY_PAD_X * 2);
}

function hasYoY(value: number | null): value is number {
  return value != null && Number.isFinite(value);
}

export function EntityRevenueChart({
  financials,
  loading = false,
  market = null,
}: EntityRevenueChartProps) {
  const { t, locale } = useTranslation();

  const currencyLabel = useMemo(() => {
    if (!market) return null;
    return t(`core.${MARKET_LEGAL_CURRENCY_KEY[market]}`);
  }, [market, t]);

  const chart = useMemo(() => {
    if (!financials.length) {
      return { barMax: 1, yoyMin: -1, yoyMax: 1 };
    }
    const barValues = financials.flatMap((f) => [f.revenue, f.netProfit]);
    const barMax = Math.max(...barValues, 1);
    const yoyValues = financials.map((f) => f.revenueYoY).filter(hasYoY);
    if (!yoyValues.length) {
      return { barMax, yoyMin: -5, yoyMax: 5 };
    }
    const yoyMin = Math.min(...yoyValues, 0);
    const yoyMax = Math.max(...yoyValues, 0);
    const yoyPad = Math.max(4, (yoyMax - yoyMin) * 0.25);
    return {
      barMax,
      yoyMin: yoyMin - yoyPad,
      yoyMax: yoyMax + yoyPad,
    };
  }, [financials]);

  const yoySegments = useMemo(() => {
    if (!financials.length) return [] as string[];

    const segments: string[] = [];
    let segment: string[] = [];

    financials.forEach((f, i) => {
      if (!hasYoY(f.revenueYoY)) {
        if (segment.length >= 2) {
          segments.push(segment.join(' '));
        }
        segment = [];
        return;
      }

      const x = yoyX(i, financials.length);
      const y = chartY(f.revenueYoY, chart.yoyMin, chart.yoyMax, YOY_H, YOY_PAD_Y);
      segment.push(`${x},${y}`);
    });

    if (segment.length >= 2) {
      segments.push(segment.join(' '));
    }

    return segments;
  }, [financials, chart.yoyMin, chart.yoyMax]);

  return (
    <EntityCard
      title={t('entityPage.revenueTitle')}
      className="entity-card--revenue"
      actions={
        <div className="core-revenue__legend core-revenue__legend--inline">
          <span className="core-revenue__legend-item core-revenue__legend-item--revenue">
            {currencyLabel
              ? t('entityPage.revenueWithCurrency', { currency: currencyLabel })
              : t('entityPage.revenue')}
          </span>
          <span className="core-revenue__legend-item core-revenue__legend-item--profit">
            {currencyLabel
              ? t('entityPage.netProfitWithCurrency', { currency: currencyLabel })
              : t('entityPage.netProfit')}
          </span>
          <span className="core-revenue__legend-item core-revenue__legend-item--yoy">
            {t('entityPage.revenueYoY')}
          </span>
        </div>
      }
    >
      <div className="core-revenue">
        {loading && !financials.length ? (
          <LoadingIndicator
            className="entity-chart-stage__status"
            label={t('entityPage.finIndicatorsLoading')}
            variant="panel"
          />
        ) : null}
        {!loading && !financials.length ? (
          <p className="entity-chart-stage__status">{t('entityPage.finIndicatorsEmpty')}</p>
        ) : null}

        {financials.length ? (
          <div className="core-revenue__stage">
            <div className="core-revenue__yoy-panel" aria-hidden>
              <svg
                viewBox={`0 0 ${YOY_W} ${YOY_H}`}
                preserveAspectRatio="none"
                className="core-revenue__yoy-svg"
              >
                <line
                  x1={YOY_PAD_X}
                  x2={YOY_W - YOY_PAD_X}
                  y1={chartY(0, chart.yoyMin, chart.yoyMax, YOY_H, YOY_PAD_Y)}
                  y2={chartY(0, chart.yoyMin, chart.yoyMax, YOY_H, YOY_PAD_Y)}
                  className="core-revenue__yoy-zero"
                />
                {yoySegments.map((points, index) => (
                  <polyline key={`yoy-seg-${index}`} points={points} className="core-revenue__yoy-line" />
                ))}
                {financials.map((f, i) => {
                  if (!hasYoY(f.revenueYoY)) return null;
                  const x = yoyX(i, financials.length);
                  const y = chartY(f.revenueYoY, chart.yoyMin, chart.yoyMax, YOY_H, YOY_PAD_Y);
                  return (
                    <circle
                      key={`${f.reportDate || f.year}-yoy-dot`}
                      cx={x}
                      cy={y}
                      r="2.6"
                      className={`core-revenue__yoy-dot core-revenue__yoy-dot--${
                        f.revenueYoY >= 0 ? 'up' : 'down'
                      }`}
                    />
                  );
                })}
              </svg>
              <div className="core-revenue__yoy-labels">
                {financials.map((f, i) => {
                  if (!hasYoY(f.revenueYoY)) return null;
                  return (
                    <span
                      key={`${f.reportDate || f.year}-yoy-label`}
                      className={`core-revenue__yoy-label core-revenue__yoy-label--${
                        f.revenueYoY >= 0 ? 'up' : 'down'
                      }`}
                      style={{ left: `${columnCenterPct(i, financials.length)}%` }}
                      title={f.year}
                    >
                      {formatSignedPercent(f.revenueYoY)}
                    </span>
                  );
                })}
              </div>
            </div>

            <div className="core-revenue__columns">
              {financials.map((f) => {
                const revPct = Math.max(4, (f.revenue / chart.barMax) * 100);
                const profitPct = Math.max(4, (f.netProfit / chart.barMax) * 100);
                return (
                  <div key={f.reportDate || f.year} className="core-revenue__col" title={f.year}>
                    <div className="core-revenue__figures">
                      <span className="core-revenue__figure core-revenue__figure--revenue">
                        {formatFinancialAmount(f.revenue, locale)}
                      </span>
                      <span className="core-revenue__figure core-revenue__figure--profit">
                        {formatFinancialAmount(f.netProfit, locale)}
                      </span>
                    </div>
                    <div className="core-revenue__bar-group">
                      <div className="core-revenue__bar-slot">
                        <div
                          className="core-revenue__bar core-revenue__bar--revenue"
                          style={{ height: `${revPct}%` }}
                        />
                      </div>
                      <div className="core-revenue__bar-slot">
                        <div
                          className="core-revenue__bar core-revenue__bar--profit"
                          style={{ height: `${profitPct}%` }}
                        />
                      </div>
                    </div>
                    <span className="core-revenue__period">{f.year}</span>
                  </div>
                );
              })}
            </div>
          </div>
        ) : null}
      </div>
    </EntityCard>
  );
}
