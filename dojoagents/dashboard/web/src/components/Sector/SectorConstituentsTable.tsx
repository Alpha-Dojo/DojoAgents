import { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useSectorConstituents } from '../../hooks/useSectorConstituents';
import { useTranslation } from '../../hooks/useTranslation';
import type { MarketCode } from '../../types/market';
import type { SectorConstituentItem, SectorLevelKey } from '../../types/sector';
import type { SectorPathSelection } from '../../types/sectorTaxonomy';
import { MARKET_CODE, MARKET_FLAG_IMAGE } from '../../utils/marketDisplay';
import {
  formatMarketCap,
  formatPe,
  formatStockPrice,
  isNegativeValuationRatio,
} from '../../utils/marketStats';

import type { AppTab } from '../../navigation/appTab';
import { openEntityTicker } from '../../navigation/openEntityTicker';
import { LoadingIndicator } from '../ui/LoadingIndicator';

interface SectorConstituentsTableProps {
  selection: SectorPathSelection;
  scope: SectorLevelKey;
  onNavigateTab?: (tab: AppTab) => void;
}

const MARKETS: MarketCode[] = ['us', 'cn', 'hk'];

const TABLE_COLGROUP = (
  <colgroup>
    <col className="sphere-table__col-code" />
    <col className="sphere-table__col-name" />
    <col className="sphere-table__col-price" />
    <col className="sphere-table__col-day" />
    <col className="sphere-table__col-year" />
    <col className="sphere-table__col-cap" />
    <col className="sphere-table__col-pe" />
    <col className="sphere-table__col-pb" />
    <col className="sphere-table__col-scrollbar" />
  </colgroup>
);

type SortKey = 'market_cap' | 'change_percent' | 'window_change_percent' | 'pe' | 'pb';
type SortDir = 'asc' | 'desc';

function formatPercent(value: number | null | undefined, signed = true): string {
  if (value == null || Number.isNaN(value)) return '—';
  const prefix = signed && value > 0 ? '+' : '';
  return `${prefix}${value.toFixed(2)}%`;
}

function sortValue(row: SectorConstituentItem, key: SortKey): number | null {
  if (key === 'market_cap') return row.market_cap;
  if (key === 'change_percent') return row.change_percent;
  if (key === 'window_change_percent') return row.window_change_percent;
  if (key === 'pe') return row.pe;
  return row.pb;
}

function sortItems(items: SectorConstituentItem[], key: SortKey, dir: SortDir): SectorConstituentItem[] {
  const factor = dir === 'asc' ? 1 : -1;
  return [...items].sort((a, b) => {
    const av = sortValue(a, key);
    const bv = sortValue(b, key);
    if (av == null && bv == null) return a.ticker.localeCompare(b.ticker);
    if (av == null) return 1;
    if (bv == null) return -1;
    if (av === bv) return a.ticker.localeCompare(b.ticker);
    return (av - bv) * factor;
  });
}

function SortIndicator({ active, dir }: { active: boolean; dir: SortDir }) {
  if (!active) {
    return (
      <span className="sphere-table-sort__icon sphere-table-sort__icon--idle" aria-hidden>
        ↕
      </span>
    );
  }
  return (
    <span className="sphere-table-sort__icon" aria-hidden>
      {dir === 'asc' ? '↑' : '↓'}
    </span>
  );
}

function ConstituentNameCell({ name }: { name: string }) {
  const textRef = useRef<HTMLSpanElement>(null);
  const [tooltip, setTooltip] = useState<{ x: number; y: number } | null>(null);

  const showTooltip = () => {
    const el = textRef.current;
    if (!el || el.scrollWidth <= el.clientWidth + 1) return;
    const rect = el.getBoundingClientRect();
    setTooltip({ x: rect.left, y: rect.top - 6 });
  };

  const hideTooltip = () => setTooltip(null);

  return (
    <td className="sphere-table__name">
      <span
        ref={textRef}
        className="sphere-table__name-text"
        onMouseEnter={showTooltip}
        onMouseLeave={hideTooltip}
        onFocus={showTooltip}
        onBlur={hideTooltip}
        tabIndex={0}
      >
        {name}
      </span>
      {tooltip
        ? createPortal(
            <div
              className="sphere-table__name-tooltip"
              style={{ left: tooltip.x, top: tooltip.y }}
              role="tooltip"
            >
              {name}
            </div>,
            document.body,
          )
        : null}
    </td>
  );
}

function ConstituentsMarketColumn({
  market,
  items,
  loading,
  onTickerClick,
}: {
  market: MarketCode;
  items: SectorConstituentItem[];
  loading: boolean;
  onTickerClick?: (row: SectorConstituentItem) => void;
}) {
  const { t, text } = useTranslation();
  const [sortKey, setSortKey] = useState<SortKey>('market_cap');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  useEffect(() => {
    setSortKey('market_cap');
    setSortDir('desc');
  }, [items]);

  const sortedItems = useMemo(
    () => sortItems(items, sortKey, sortDir),
    [items, sortKey, sortDir],
  );

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((dir) => (dir === 'asc' ? 'desc' : 'asc'));
      return;
    }
    setSortKey(key);
    setSortDir('desc');
  };

  const sortLabel: Record<SortKey, string> = {
    market_cap: t('sectorPage.sortByMarketCap'),
    change_percent: t('sectorPage.sortByDayChange'),
    window_change_percent: t('sectorPage.sortByYearChange'),
    pe: t('sectorPage.sortByPe'),
    pb: t('sectorPage.sortByPb'),
  };

  const renderSortHeader = (key: SortKey, label: string) => (
    <th>
      <button
        type="button"
        className={`sphere-table-sort ${sortKey === key ? 'sphere-table-sort--active' : ''}`}
        aria-label={sortLabel[key]}
        title={sortLabel[key]}
        onClick={() => toggleSort(key)}
      >
        <span>{label}</span>
        <SortIndicator active={sortKey === key} dir={sortDir} />
      </button>
    </th>
  );

  return (
    <section className="sphere-constituents-col" aria-label={MARKET_CODE[market]}>
      <header className="sphere-constituents-col__head">
        <img className="sphere-constituents-col__flag" src={MARKET_FLAG_IMAGE[market]} alt="" aria-hidden />
        <span className="sphere-constituents-col__code">{MARKET_CODE[market]}</span>
      </header>
      <div className="sphere-table-wrap sphere-table-wrap--split">
        {loading && items.length === 0 ? (
          <LoadingIndicator
            className="sphere-table-card__status"
            label={t('sectorPage.loading')}
            variant="panel"
          />
        ) : null}
        <div className="sphere-table-head">
          <table className="sphere-table">
            {TABLE_COLGROUP}
            <thead>
              <tr>
                <th>{t('sectorPage.colCode')}</th>
                <th>{t('sectorPage.colName')}</th>
                <th>{t('sectorPage.colPrice')}</th>
                {renderSortHeader('change_percent', t('sectorPage.colDay'))}
                {renderSortHeader('window_change_percent', t('sectorPage.colYear'))}
                {renderSortHeader('market_cap', t('sectorPage.colMarketCap'))}
                {renderSortHeader('pe', t('sectorPage.colPe'))}
                {renderSortHeader('pb', t('sectorPage.colPb'))}
                <th className="sphere-table__scrollbar-cell" aria-hidden />
              </tr>
            </thead>
          </table>
        </div>
        <div className="sphere-table-scroll">
          <table className="sphere-table">
            {TABLE_COLGROUP}
            <tbody>
              {sortedItems.map((row) => {
                const dayChange = row.change_percent;
                const yearChange = row.window_change_percent;
                const upDay = dayChange != null && dayChange >= 0;
                const upYear = yearChange != null && yearChange >= 0;
                const fullName = text(row.name);
                return (
                  <tr key={row.ticker}>
                  <td>
                    <button
                      type="button"
                      className="sphere-table__ticker sphere-table__ticker-link"
                      title={t('entityPage.openTicker')}
                      aria-label={`${t('entityPage.openTicker')}: ${row.ticker}`}
                      onClick={() => onTickerClick?.(row)}
                    >
                      {row.ticker}
                    </button>
                  </td>
                    <ConstituentNameCell name={fullName} />
                    <td>{formatStockPrice(row.last_price)}</td>
                    <td
                      className={
                        dayChange == null ? undefined : upDay ? 'sphere-table__up' : 'sphere-table__down'
                      }
                    >
                      {formatPercent(dayChange)}
                    </td>
                    <td
                      className={
                        yearChange == null ? undefined : upYear ? 'sphere-table__up' : 'sphere-table__down'
                      }
                    >
                      {formatPercent(yearChange)}
                    </td>
                    <td>{row.market_cap != null ? formatMarketCap(row.market_cap) : '—'}</td>
                    <td className={isNegativeValuationRatio(row.pe) ? 'sphere-table__ratio--negative' : undefined}>
                      {formatPe(row.pe, { lossLabel: t('valuation.peLoss') })}
                    </td>
                    <td className={isNegativeValuationRatio(row.pb) ? 'sphere-table__ratio--negative' : undefined}>
                      {formatPe(row.pb)}
                    </td>
                    <td className="sphere-table__scrollbar-cell" aria-hidden />
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}

export function SectorConstituentsTable({
  selection,
  scope,
  onNavigateTab,
}: SectorConstituentsTableProps) {
  const { byMarket, loading, error } = useSectorConstituents(selection, scope);

  const handleTickerClick = (row: SectorConstituentItem) => {
    openEntityTicker(onNavigateTab, {
      ticker: row.ticker,
      market: row.market,
      name_zh: row.name.zh,
      name_en: row.name.en,
      sector_source: 'navigation',
      sector_selection: selection,
    });
  };

  return (
    <>
      {error ? <p className="sphere-table-card__status">{error}</p> : null}
      <div className="sphere-constituents-grid">
        {MARKETS.map((market) => (
          <ConstituentsMarketColumn
            key={market}
            market={market}
            items={byMarket[market]}
            loading={loading}
            onTickerClick={handleTickerClick}
          />
        ))}
      </div>
    </>
  );
}
