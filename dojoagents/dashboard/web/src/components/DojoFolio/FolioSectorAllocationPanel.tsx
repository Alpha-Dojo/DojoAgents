import { useMemo, useState } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import type { MarketCode } from '../../types/dojoMesh';
import type { FolioHolding } from '../../types/dojoFolio';
import { FOLIO_MARKETS } from '../../types/dojoFolio';
import { buildDonutPaths } from '../../utils/coreIncomeDistribution';
import { formatFolioCurrency, formatSignedPercent } from '../../utils/folioFormat';
import {
  marketHoldingsTotal,
  prepareFolioSectorSlices,
  type FolioSectorSlice,
} from '../../utils/folioSectorAllocation';
import { FolioMarketLabel } from './FolioMarketLabel';

interface FolioSectorAllocationPanelProps {
  holdings: FolioHolding[];
  loading?: boolean;
}

const DONUT_CX = 50;
const DONUT_CY = 50;
const DONUT_OUTER_R = 46;
const DONUT_INNER_R = 32;

function marketCurrency(market: MarketCode): string {
  if (market === 'sh') return 'CNY';
  if (market === 'hk') return 'HKD';
  return 'USD';
}

interface MarketSectorChartProps {
  market: MarketCode;
  holdings: FolioHolding[];
}

function MarketSectorChart({ market, holdings }: MarketSectorChartProps) {
  const { t } = useTranslation();
  const [hoveredKey, setHoveredKey] = useState<string | null>(null);

  const slices = useMemo(
    () => prepareFolioSectorSlices(holdings, market),
    [holdings, market],
  );

  const paths = useMemo(
    () => buildDonutPaths(slices, DONUT_CX, DONUT_CY, DONUT_OUTER_R, DONUT_INNER_R),
    [slices],
  );

  const totalValue = useMemo(() => marketHoldingsTotal(holdings, market), [holdings, market]);

  const activeKey = hoveredKey ?? slices[0]?.key ?? null;

  const activeSlice = useMemo((): FolioSectorSlice | null => {
    if (!slices.length) return null;
    if (!activeKey) return slices[0];
    return slices.find((slice) => slice.key === activeKey) ?? slices[0];
  }, [activeKey, slices]);

  return (
    <section className="folio-sector__chart" aria-label={t('folio.allocationTitle')}>
      <h4 className="folio-sector__chart-title">
        <FolioMarketLabel market={market} />
      </h4>

      {!slices.length ? (
        <p className="folio-sector__empty">
          <span>{t('folio.noHoldingsPrefix')}</span>
          <FolioMarketLabel market={market} />
          <span>{t('folio.noHoldingsSuffix')}</span>
        </p>
      ) : (
        <div className="folio-sector__chart-body">
          <div className="folio-sector__donut-wrap">
            <svg viewBox="0 0 100 100" className="folio-sector__donut" role="img">
              {paths.map((segment) => {
                const isActive = !activeKey || activeKey === segment.key;
                return (
                  <path
                    key={segment.key}
                    d={segment.path}
                    fill={segment.color}
                    className={`folio-sector__donut-segment${isActive ? '' : ' folio-sector__donut-segment--dim'}${
                      activeKey === segment.key ? ' folio-sector__donut-segment--active' : ''
                    }`}
                    onMouseEnter={() => setHoveredKey(segment.key)}
                    onMouseLeave={() => setHoveredKey(null)}
                  />
                );
              })}
            </svg>
            <div className="folio-sector__donut-center" aria-hidden>
              <span className="folio-sector__donut-center-total">
                {formatFolioCurrency(totalValue, marketCurrency(market))}
              </span>
            </div>
          </div>

          {activeSlice ? (
            <p
              className="folio-sector__detail-line"
              title={`${activeSlice.name} ${formatFolioCurrency(activeSlice.value, marketCurrency(market))} ${(activeSlice.ratio * 100).toFixed(1)}% ${formatSignedPercent(activeSlice.returnPercent)}`}
            >
              <span
                className="folio-sector__detail-dot"
                style={{ backgroundColor: activeSlice.color }}
                aria-hidden
              />
              <span className="folio-sector__detail-name">{activeSlice.name}</span>
              <span className="folio-sector__detail-metrics">
                <span className="folio-sector__detail-amount">
                  {formatFolioCurrency(activeSlice.value, marketCurrency(market))}
                </span>
                <span className="folio-sector__detail-ratio">
                  {(activeSlice.ratio * 100).toFixed(1)}%
                </span>
                <span
                  className={`folio-sector__detail-return folio-tone--${
                    activeSlice.returnPercent >= 0 ? 'up' : 'down'
                  }`}
                >
                  {formatSignedPercent(activeSlice.returnPercent)}
                </span>
              </span>
            </p>
          ) : null}
        </div>
      )}
    </section>
  );
}

export function FolioSectorAllocationPanel({
  holdings,
  loading = false,
}: FolioSectorAllocationPanelProps) {
  const { t } = useTranslation();

  return (
    <article className="folio-card folio-sector">
      <header className="folio-card__head">
        <h3 className="folio-card__title">{t('folio.allocationTitle')}</h3>
      </header>
      {loading ? (
        <p className="folio-sector__loading">{t('folio.loading')}</p>
      ) : (
        <div className="folio-sector__grid">
          {FOLIO_MARKETS.map((market) => (
            <MarketSectorChart key={market} market={market} holdings={holdings} />
          ))}
        </div>
      )}
    </article>
  );
}
