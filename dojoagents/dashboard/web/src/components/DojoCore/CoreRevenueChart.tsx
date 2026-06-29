import { useMemo } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import type { CoreFinancialYear } from '../../types/dojoCore';
import type { MarketCode } from '../../types/dojoMesh';
import {
  chartY,
  formatFinancialAmount,
  formatSignedPercent,
} from '../../utils/coreCharts';
import { MARKET_LEGAL_CURRENCY_KEY } from '../../utils/marketDisplay';
import { LoadingIndicator } from '../ui/LoadingIndicator';
import { CoreCard } from './CoreCard';

interface CoreRevenueChartProps {
  financials: CoreFinancialYear[];
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

export function CoreRevenueChart({
  financials,
  loading = false,
  market = null,
}: CoreRevenueChartProps) {
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
    <CoreCard
      title={t('core.revenueTitle')}
      className="core-card--revenue"
      actions={
        <div className="core-revenue__legend core-revenue__legend--inline">
          <span className="core-revenue__legend-item core-revenue__legend-item--revenue">
            {currencyLabel
              ? t('core.revenueWithCurrency', { currency: currencyLabel })
              : t('core.revenue')}
          </span>
          <span className="core-revenue__legend-item core-revenue__legend-item--profit">
            {currencyLabel
              ? t('core.netProfitWithCurrency', { currency: currencyLabel })
              : t('core.netProfit')}
          </span>
          <span className="core-revenue__legend-item core-revenue__legend-item--yoy">
            {t('core.revenueYoY')}
          </span>
        </div>
      }
    >
      <div className="core-revenue">
        {loading && !financials.length ? (
          <LoadingIndicator
            className="core-chart-stage__status"
            label={t('core.finIndicatorsLoading')}
            variant="panel"
          />
        ) : null}
        {!loading && !financials.length ? (
          <p className="core-chart-stage__status">{t('core.finIndicatorsEmpty')}</p>
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
    </CoreCard>
  );
}
