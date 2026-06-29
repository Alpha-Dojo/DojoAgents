import { useCallback, useMemo, useState } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import { useSectorTaxonomy } from '../../hooks/useSectorTaxonomy';
import type { AppTab } from '../../navigation/appTab';
import { openSphereFromSelection } from '../../navigation/openSector';
import type { SectorLevelKey } from '../../types/sector';
import type { MarketCode } from '../../types/market';
import type { FolioHolding } from '../../types/folio';
import { FOLIO_MARKETS } from '../../types/folio';
import { buildDonutPaths } from '../../utils/entityIncomeDistribution';
import { formatFolioCompactCurrency, formatFolioCurrency, formatSignedPercent } from '../../utils/folioFormat';
import {
  marketHoldingsTotal,
  prepareFolioSectorSlices,
  type FolioSectorLevel,
  type FolioSectorSlice,
} from '../../utils/folioSectorAllocation';
import { findSectorPathByLevelName, selectionFromPath } from '../../utils/sectorTaxonomy';
import { FolioMarketLabel } from './FolioMarketLabel';

interface FolioSectorAllocationPanelProps {
  embedded?: boolean;
  holdings: FolioHolding[];
  loading?: boolean;
  sectorLevel?: SectorLevelKey;
  onSectorLevelChange?: (level: SectorLevelKey) => void;
  onNavigateTab?: (tab: AppTab) => void;
}

const SECTOR_LEVELS: SectorLevelKey[] = ['L1', 'L2', 'L3'];

interface FolioSectorLevelTabsProps {
  sectorLevel: SectorLevelKey;
  onSectorLevelChange: (level: SectorLevelKey) => void;
  className?: string;
}

export function FolioSectorLevelTabs({
  sectorLevel,
  onSectorLevelChange,
  className,
}: FolioSectorLevelTabsProps) {
  const { t } = useTranslation();

  return (
    <div
      className={`folio-sector__level-tabs${className ? ` ${className}` : ''}`}
      role="tablist"
      aria-label={t('entityPage.sectorPeLevel')}
    >
      {SECTOR_LEVELS.map((level) => (
        <button
          key={level}
          type="button"
          role="tab"
          aria-selected={sectorLevel === level}
          className={`folio-sector__level-tab${sectorLevel === level ? ' folio-sector__level-tab--active' : ''}`}
          onClick={() => onSectorLevelChange(level)}
        >
          {t(level === 'L1' ? 'sectorPage.level1' : level === 'L2' ? 'sectorPage.level2' : 'sectorPage.level3')}
        </button>
      ))}
    </div>
  );
}

const DONUT_CX = 50;
const DONUT_CY = 50;
const DONUT_OUTER_R = 46;
const DONUT_INNER_R = 32;

function marketCurrency(market: MarketCode): string {
  if (market === 'cn') return 'CNY';
  if (market === 'hk') return 'HKD';
  return 'USD';
}

interface MarketSectorChartProps {
  market: MarketCode;
  holdings: FolioHolding[];
  level: FolioSectorLevel;
  onNavigateTab?: (tab: AppTab) => void;
}

function MarketSectorChart({ market, holdings, level, onNavigateTab }: MarketSectorChartProps) {
  const { t } = useTranslation();
  const { taxonomy } = useSectorTaxonomy();
  const [hoveredKey, setHoveredKey] = useState<string | null>(null);

  const slices = useMemo(
    () => prepareFolioSectorSlices(holdings, market, level),
    [holdings, level, market],
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

  const canOpenSector =
    Boolean(activeSlice?.name && activeSlice.name !== '其他' && taxonomy && onNavigateTab);

  const handleOpenSector = useCallback(() => {
    if (!activeSlice || !taxonomy || !onNavigateTab || activeSlice.name === '其他') return;
    const path = findSectorPathByLevelName(taxonomy, level, activeSlice.name);
    if (!path) return;
    openSphereFromSelection(onNavigateTab, selectionFromPath(path), level);
  }, [activeSlice, level, onNavigateTab, taxonomy]);

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
                {formatFolioCompactCurrency(totalValue, marketCurrency(market))}
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
              {canOpenSector ? (
                <button
                  type="button"
                  className="folio-sector__detail-name folio-sector__detail-link"
                  onClick={handleOpenSector}
                  title={t('sector.jumpSphere')}
                >
                  {activeSlice.name}
                </button>
              ) : (
                <span className="folio-sector__detail-name">{activeSlice.name}</span>
              )}
              <span className="folio-sector__detail-metrics">
                <span className="folio-sector__detail-amount">
                  {formatFolioCompactCurrency(activeSlice.value, marketCurrency(market))}
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
  embedded = false,
  holdings,
  loading = false,
  sectorLevel: sectorLevelProp,
  onSectorLevelChange,
  onNavigateTab,
}: FolioSectorAllocationPanelProps) {
  const { t } = useTranslation();
  const [internalSectorLevel, setInternalSectorLevel] = useState<SectorLevelKey>('L1');
  const sectorLevel = sectorLevelProp ?? internalSectorLevel;
  const setSectorLevel = onSectorLevelChange ?? setInternalSectorLevel;

  const body = loading ? (
    <p className="folio-sector__loading">{t('folio.loading')}</p>
  ) : (
    <div className="folio-sector__grid">
      {FOLIO_MARKETS.map((market) => (
        <MarketSectorChart
          key={market}
          market={market}
          holdings={holdings}
          level={sectorLevel}
          onNavigateTab={onNavigateTab}
        />
      ))}
    </div>
  );

  if (embedded) {
    return (
      <div className="folio-sector folio-sector--embedded">
        {body}
      </div>
    );
  }

  return (
    <article className="folio-card folio-sector">
      <header className="folio-card__head folio-card__head--compact">
        <h3 className="folio-card__title">{t('folio.allocationTitle')}</h3>
        <FolioSectorLevelTabs
          sectorLevel={sectorLevel}
          onSectorLevelChange={setSectorLevel}
        />
      </header>
      {body}
    </article>
  );
}
