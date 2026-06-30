import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import type { FolioPortfolioDetail } from '../../api/folio';
import type { AppTab } from '../../navigation/appTab';
import type { MarketCode } from '../../types/market';
import { FOLIO_MARKETS } from '../../types/folio';
import { formatCompactAmount, formatSignedPercent } from '../../utils/folioFormat';
import {
  sortFolioCandidates,
  type FolioCandidatesSortDir,
  type FolioCandidatesSortKey,
} from '../../utils/folioCandidatesSort';
import { formatPe, formatStockPrice } from '../../utils/marketStats';
import { localizedStockName } from '../../utils/stockDisplay';
import { openEntityTicker } from '../../navigation/openEntityTicker';
import { FolioAddHoldingSearch } from './FolioAddHoldingSearch';
import { FolioHoldingNameCell } from './FolioHoldingNameCell';
import { FolioMarketLabel } from './FolioMarketLabel';
import { TrashIcon } from './FolioSidebarIcons';
import { LoadingIndicator } from '../ui/LoadingIndicator';
import { DojoButton } from '../ui';

interface FolioCandidatesPanelProps {
  portfolio: FolioPortfolioDetail;
  loading?: boolean;
  addingTicker?: boolean;
  removingTicker?: string | null;
  onNavigateTab?: (tab: AppTab) => void;
  onAddCandidate: (ticker: string, market: MarketCode) => void;
  onRemoveCandidate: (ticker: string, market: MarketCode) => void;
  onCreateOrder: (context: { market: MarketCode; ticker: string; price: number; name: string }) => void;
}

function formatOptional(value: number | null | undefined, formatter: (n: number) => string): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return formatter(value);
}

function SortIndicator({ active, dir }: { active: boolean; dir: FolioCandidatesSortDir }) {
  if (!active) {
    return (
      <span className="folio-table-sort__icon folio-table-sort__icon--idle" aria-hidden>
        ↕
      </span>
    );
  }
  return (
    <span className="folio-table-sort__icon" aria-hidden>
      {dir === 'asc' ? '↑' : '↓'}
    </span>
  );
}

export function FolioCandidatesPanel({
  portfolio,
  loading = false,
  addingTicker = false,
  removingTicker = null,
  onNavigateTab,
  onAddCandidate,
  onRemoveCandidate,
  onCreateOrder,
}: FolioCandidatesPanelProps) {
  const { t, locale } = useTranslation();
  const [sortKey, setSortKey] = useState<FolioCandidatesSortKey | null>(null);
  const [sortDir, setSortDir] = useState<FolioCandidatesSortDir>('desc');

  useEffect(() => {
    setSortKey(null);
    setSortDir('desc');
  }, [portfolio.id]);

  const candidatesByMarket = useMemo(() => {
    const grouped: Record<MarketCode, FolioPortfolioDetail['candidates']> = { us: [], cn: [], hk: [] };
    for (const row of portfolio.candidates) {
      grouped[row.market].push(row);
    }
    for (const market of FOLIO_MARKETS) {
      if (sortKey) {
        grouped[market] = sortFolioCandidates(grouped[market], sortKey, sortDir);
      }
    }
    return grouped;
  }, [portfolio.candidates, sortDir, sortKey]);

  const existingTickersByMarket = useMemo(() => {
    const map: Record<MarketCode, Set<string>> = { us: new Set(), cn: new Set(), hk: new Set() };
    for (const row of portfolio.candidates) {
      map[row.market].add(row.ticker);
    }
    return map;
  }, [portfolio.candidates]);

  const heldTickersByMarket = useMemo(() => {
    const map: Record<MarketCode, Set<string>> = { us: new Set(), cn: new Set(), hk: new Set() };
    for (const row of portfolio.positions) {
      if (row.shares > 0) {
        map[row.market].add(row.ticker);
      }
    }
    return map;
  }, [portfolio.positions]);

  const sortLabels: Record<FolioCandidatesSortKey, string> = {
    price: t('folio.colPrice'),
    changePercent: t('folio.colChange'),
    marketCap: t('folio.colMarketCap'),
    pe: t('folio.colPe'),
    pb: t('folio.colPb'),
    dividendYield: t('folio.colDividendYield'),
    eps: t('folio.colEps'),
    turnRate: t('folio.colTurnover'),
  };

  const toggleSort = (key: FolioCandidatesSortKey) => {
    if (sortKey === key) {
      setSortDir((dir) => (dir === 'asc' ? 'desc' : 'asc'));
      return;
    }
    setSortKey(key);
    setSortDir('desc');
  };

  const renderSortHeader = (key: FolioCandidatesSortKey) => (
    <button
      type="button"
      className={`folio-table-sort folio-table-sort--center ${
        sortKey === key ? 'folio-table-sort--active' : ''
      }`}
      aria-label={t('folio.sortByColumn', { column: sortLabels[key] })}
      onClick={() => toggleSort(key)}
    >
      <span>{sortLabels[key]}</span>
      <SortIndicator active={sortKey === key} dir={sortDir} />
    </button>
  );

  const showLoading = loading && portfolio.candidates.length === 0;

  return (
    <div className="folio-holdings folio-candidates">
      {showLoading ? (
        <div className="folio-holdings__loading">
          <LoadingIndicator label={t('folio.loading')} />
        </div>
      ) : (
        <div className="folio-holdings__markets">
          {FOLIO_MARKETS.map((market) => {
            const rows = candidatesByMarket[market];
            return (
              <section key={market} className={`folio-holdings__market folio-holdings__market--${market}`}>
                <header className="folio-holdings__market-head">
                  <FolioMarketLabel market={market} />
                  <FolioAddHoldingSearch
                    market={market}
                    existingTickers={existingTickersByMarket[market]}
                    adding={addingTicker}
                    placement="trailing"
                    onAdd={onAddCandidate}
                  />
                </header>

                <div className="folio-holdings__table-scroll">
                  <table className="folio-table folio-table--candidates">
                    <thead>
                      <tr>
                        <th>{t('folio.colTicker')}</th>
                        <th>{t('folio.colName')}</th>
                        <th className="folio-table__num">{renderSortHeader('price')}</th>
                        <th className="folio-table__num">{renderSortHeader('changePercent')}</th>
                        <th className="folio-table__num">{renderSortHeader('marketCap')}</th>
                        <th className="folio-table__num">{renderSortHeader('pe')}</th>
                        <th className="folio-table__num">{renderSortHeader('pb')}</th>
                        <th className="folio-table__num">{renderSortHeader('dividendYield')}</th>
                        <th className="folio-table__num">{renderSortHeader('eps')}</th>
                        <th className="folio-table__num">{renderSortHeader('turnRate')}</th>
                        <th className="folio-table__action-head" aria-label={t('folio.colActions')} />
                        <th className="folio-table__remove-head" aria-label={t('folio.colActions')} />
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((row) => {
                          const positive = row.changePercent >= 0;
                          const isHeld = heldTickersByMarket[market].has(row.ticker);
                          const localizedName = localizedStockName(
                            { zh: row.nameZh, en: row.nameEn, fallback: row.name },
                            locale,
                          );
                          return (
                            <tr key={`${market}:${row.ticker}`}>
                              <td className="folio-table__ticker-cell">
                                <button
                                  type="button"
                                  className="folio-table__ticker folio-table__ticker-link"
                                  onClick={() =>
                                    openEntityTicker(onNavigateTab, {
                                      ticker: row.ticker,
                                      market: row.market,
                                      name_zh: row.nameZh,
                                      name_en: row.nameEn,
                                    })
                                  }
                                >
                                  {row.ticker}
                                </button>
                              </td>
                              <FolioHoldingNameCell name={localizedName} />
                              <td className={`folio-table__num ${positive ? 'sphere-table__up' : 'sphere-table__down'}`}>
                                {formatStockPrice(row.price)}
                              </td>
                              <td className={`folio-table__num ${positive ? 'sphere-table__up' : 'sphere-table__down'}`}>
                                {formatSignedPercent(row.changePercent)}
                              </td>
                              <td className="folio-table__num">{formatCompactAmount(row.marketCap)}</td>
                              <td className="folio-table__num">{row.pe != null ? formatPe(row.pe) : '—'}</td>
                              <td className="folio-table__num">{formatOptional(row.pb, (v) => v.toFixed(2))}</td>
                              <td className="folio-table__num">
                                {formatOptional(row.dividendYield, (v) => `${v.toFixed(2)}%`)}
                              </td>
                              <td className="folio-table__num">{formatOptional(row.eps, (v) => v.toFixed(2))}</td>
                              <td className="folio-table__num">
                                {formatOptional(row.turnRate, (v) => `${v.toFixed(2)}%`)}
                              </td>
                              <td className="folio-table__action-cell">
                                <button
                                  type="button"
                                  className="folio-table__trade"
                                  aria-label={t('folio.createOrderFor', { ticker: row.ticker })}
                                  title={t('folio.createOrder')}
                                  onClick={() =>
                                    onCreateOrder({
                                      market: row.market,
                                      ticker: row.ticker,
                                      price: row.price,
                                      name: localizedName,
                                    })
                                  }
                                >
                                  <span aria-hidden>↗</span>
                                </button>
                              </td>
                              <td className="folio-table__remove-cell">
                                <DojoButton
                                    icon
                                    size="xs"
                                    variant="error"
                                    className="dojo-agent-olio-table__remove-delete"
                                    aria-label={t('folio.removeHolding', { ticker: row.ticker })}
                                  disabled={removingTicker === row.ticker || isHeld}
                                  title={isHeld ? t('folio.candidateHeldLocked') : undefined}
                                  onClick={() => onRemoveCandidate(row.ticker, row.market)}
                                  >
                                    <TrashIcon />
                                </DojoButton>
                              </td>
                            </tr>
                          );
                        })}
                    </tbody>
                  </table>
                </div>
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}
