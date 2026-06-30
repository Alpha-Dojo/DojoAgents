import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import type { FolioPortfolioDetail } from '../../api/folio';
import type { AppTab } from '../../navigation/appTab';
import { openEntityTicker } from '../../navigation/openEntityTicker';
import type { MarketCode } from '../../types/market';
import { DEFAULT_FOLIO_CONFIG, FOLIO_MARKETS } from '../../types/folio';
import { normalizeManualShares, sharesInputStep, formatSharesForMarket } from '../../utils/folioAllocation';
import { formatSignedPercent } from '../../utils/folioFormat';
import {
  sortFolioHoldings,
  type FolioHoldingsSortDir,
  type FolioHoldingsSortKey,
} from '../../utils/folioHoldingsSort';
import { formatStockPrice } from '../../utils/marketStats';
import { localizedStockName } from '../../utils/stockDisplay';
import { LoadingIndicator } from '../ui/LoadingIndicator';
import { FolioAddHoldingSearch } from './FolioAddHoldingSearch';
import { FolioHoldingNameCell } from './FolioHoldingNameCell';
import { FolioHoldingOpenDatePicker } from './FolioHoldingOpenDatePicker';
import { FolioLockableField } from './FolioLockableField';
import { FolioMarketLabel } from './FolioMarketLabel';
import { TrashIcon } from './FolioSidebarIcons';

interface FolioHoldingsPanelProps {
  embedded?: boolean;
  portfolio: FolioPortfolioDetail;
  loading?: boolean;
  addingTicker?: boolean;
  onNavigateTab?: (tab: AppTab) => void;
  onApplyShares: (sharesByTicker: Record<string, number>) => void;
  onToggleSharesLock: (ticker: string, locked: boolean) => void;
  onToggleOpenDateLock: (ticker: string, locked: boolean) => void;
  onToggleCostLock: (ticker: string, locked: boolean) => void;
  onApplyCost: (ticker: string, cost: number | null) => void;
  onApplyOpenDate: (ticker: string, openDate: string | null) => void;
  onAddHolding: (ticker: string, market: MarketCode) => void;
  onRemoveHolding: (ticker: string, market: MarketCode) => void;
  removingTicker?: string | null;
}

const HOLDINGS_COLGROUP = (
  <colgroup>
    <col className="folio-table__col-ticker" />
    <col className="folio-table__col-name" />
    <col className="folio-table__col-date" />
    <col className="folio-table__col-shares" />
    <col className="folio-table__col-weight" />
    <col className="folio-table__col-cost" />
    <col className="folio-table__col-price" />
    <col className="folio-table__col-change" />
    <col className="folio-table__col-total-pnl" />
    <col className="folio-table__col-remove" />
  </colgroup>
);

function costInRange(value: number, low?: number, high?: number): boolean {
  if (!Number.isFinite(value) || value <= 0) return false;
  if (low == null || high == null) return true;
  return value >= low && value <= high;
}

function resolveCostInputTitle(
  row: FolioPortfolioDetail['holdings'][number],
  costError: string | undefined,
  t: (key: string, params?: Record<string, string>) => string,
): string | undefined {
  if (costError) return costError;
  if (row.costDate && row.openDate && row.costDate !== row.openDate) {
    return t('folio.costFromTradingDay', { date: row.costDate });
  }
  if (row.costLow != null && row.costHigh != null) {
    return t('folio.costRangeHint', {
      low: row.costLow.toFixed(2),
      high: row.costHigh.toFixed(2),
    });
  }
  return undefined;
}

function SortIndicator({ active, dir }: { active: boolean; dir: FolioHoldingsSortDir }) {
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

export function FolioHoldingsPanel({
  embedded = false,
  portfolio,
  loading = false,
  addingTicker = false,
  onNavigateTab,
  onApplyShares,
  onToggleSharesLock,
  onToggleOpenDateLock,
  onToggleCostLock,
  onApplyCost,
  onApplyOpenDate,
  onAddHolding,
  onRemoveHolding,
  removingTicker = null,
}: FolioHoldingsPanelProps) {
  const { t, locale } = useTranslation();
  const [draftShares, setDraftShares] = useState<Record<string, string>>({});
  const [draftCosts, setDraftCosts] = useState<Record<string, string>>({});
  const [costErrors, setCostErrors] = useState<Record<string, string>>({});
  const [sortKey, setSortKey] = useState<FolioHoldingsSortKey | null>(null);
  const [sortDir, setSortDir] = useState<FolioHoldingsSortDir>('desc');

  const portfolioOpenDate = portfolio.config?.startDate ?? DEFAULT_FOLIO_CONFIG.startDate;
  const lockHint = t('folio.fieldLockHint');
  const unlockHint = t('folio.fieldUnlockHint');
  const holdingsCostKey = portfolio.holdings
    .map((row) => `${row.ticker}:${row.openDate ?? ''}:${row.costDate ?? ''}:${row.cost}`)
    .join('|');

  useEffect(() => {
    const nextShares: Record<string, string> = {};
    const nextCosts: Record<string, string> = {};
    for (const row of portfolio.holdings) {
      nextShares[row.ticker] = formatSharesForMarket(row.market, row.shares);
      nextCosts[row.ticker] = row.cost.toFixed(2);
    }
    setDraftShares(nextShares);
    setDraftCosts(nextCosts);
    setCostErrors({});
  }, [holdingsCostKey, portfolio.id, portfolio.sharesByTicker]);

  useEffect(() => {
    setSortKey(null);
    setSortDir('desc');
  }, [portfolio.id]);

  const sortLabels: Record<FolioHoldingsSortKey, string> = {
    openDate: t('folio.sortHoldingsByOpenDate'),
    weight: t('folio.sortHoldingsByWeight'),
    changePercent: t('folio.sortHoldingsByDayPnl'),
    totalReturnPct: t('folio.sortHoldingsByTotalPnl'),
  };

  const toggleSort = (key: FolioHoldingsSortKey) => {
    if (sortKey === key) {
      setSortDir((dir) => (dir === 'asc' ? 'desc' : 'asc'));
      return;
    }
    setSortKey(key);
    setSortDir('desc');
  };

  const renderSortHeader = (
    key: FolioHoldingsSortKey,
    label: string,
    align: 'left' | 'right',
    className = '',
  ) => (
    <th className={className}>
      <button
        type="button"
        className={`folio-table-sort folio-table-sort--${align} ${
          sortKey === key ? 'folio-table-sort--active' : ''
        }`}
        aria-label={sortLabels[key]}
        title={sortLabels[key]}
        onClick={() => toggleSort(key)}
      >
        <span>{label}</span>
        <SortIndicator active={sortKey === key} dir={sortDir} />
      </button>
    </th>
  );

  const holdingsByMarket = useMemo(() => {
    const grouped: Record<MarketCode, FolioPortfolioDetail['holdings']> = {
      us: [],
      cn: [],
      hk: [],
    };
    for (const row of portfolio.holdings) {
      grouped[row.market].push(row);
    }
    return grouped;
  }, [portfolio.holdings]);

  const existingTickersByMarket = useMemo(() => {
    const grouped: Record<MarketCode, Set<string>> = {
      us: new Set(),
      cn: new Set(),
      hk: new Set(),
    };
    for (const row of portfolio.holdings) {
      grouped[row.market].add(row.ticker);
    }
    return grouped;
  }, [portfolio.holdings]);

  const applyShareForRow = (row: FolioPortfolioDetail['holdings'][number]) => {
    if (row.sharesLocked) return;
    const draft = draftShares[row.ticker];
    if (draft == null) return;
    const normalized = normalizeManualShares(row.market, Number(draft));
    if (normalized === row.shares) return;
    const next = { ...portfolio.sharesByTicker };
    if (normalized > 0) next[row.ticker] = normalized;
    else delete next[row.ticker];
    onApplyShares(next);
  };

  const applyCostForRow = (row: FolioPortfolioDetail['holdings'][number]) => {
    if (row.costLocked) return;
    const draft = draftCosts[row.ticker];
    if (draft == null) return;
    const parsed = Number(draft);
    if (!Number.isFinite(parsed)) return;
    if (Math.abs(parsed - row.cost) <= 0.001) return;
    if (!costInRange(parsed, row.costLow, row.costHigh)) {
      setCostErrors((prev) => ({
        ...prev,
        [row.ticker]: t('folio.costOutOfRange', {
          low: row.costLow?.toFixed(2) ?? '—',
          high: row.costHigh?.toFixed(2) ?? '—',
        }),
      }));
      return;
    }
    onApplyCost(row.ticker, parsed);
  };

  const handleOpenDateChange = (row: FolioPortfolioDetail['holdings'][number], nextDate: string) => {
    if (row.openDateLocked) return;
    const usesPortfolioDefault = nextDate === portfolioOpenDate;
    onApplyOpenDate(row.ticker, usesPortfolioDefault ? null : nextDate);
  };

  const displayName = (row: FolioPortfolioDetail['holdings'][number]) =>
    localizedStockName(
      { zh: row.nameZh, en: row.nameEn, fallback: row.name },
      locale,
    );

  const hasHoldings = portfolio.holdings.length > 0;
  const showLoading = loading && !hasHoldings;

  const tableContent = (
    <>
      <div className="folio-holdings__table-wrap">
          {showLoading ? (
            <LoadingIndicator
              className="folio-holdings__empty"
              label={t('folio.loading')}
              variant="panel"
            />
          ) : (
            <div className="folio-holdings__markets">
              {FOLIO_MARKETS.map((market) => {
                const rows = holdingsByMarket[market];
                const displayRows = sortKey
                  ? sortFolioHoldings(rows, sortKey, sortDir, portfolioOpenDate)
                  : rows;
                return (
                  <section key={market} className={`folio-holdings__market folio-holdings__market--${market}`}>
                    <header className="folio-holdings__market-head">
                      <FolioMarketLabel market={market} />
                      <FolioAddHoldingSearch
                        market={market}
                        existingTickers={existingTickersByMarket[market]}
                        adding={addingTicker}
                        placement="trailing"
                        onAdd={onAddHolding}
                      />
                    </header>

                    {rows.length > 0 ? (
                      <div className="folio-holdings__table-scroll">
                        <table className="folio-table folio-table--holdings">
                          {HOLDINGS_COLGROUP}
                          <thead>
                            <tr>
                              <th>{t('folio.colTicker')}</th>
                              <th>{t('folio.colName')}</th>
                              {renderSortHeader('openDate', t('folio.colOpenDate'), 'left')}
                              <th className="folio-table__num">{t('folio.colShares')}</th>
                              {renderSortHeader('weight', t('folio.colWeight'), 'right', 'folio-table__num')}
                              <th className="folio-table__num">{t('folio.colCost')}</th>
                              <th className="folio-table__num">{t('folio.colPrice')}</th>
                              {renderSortHeader(
                                'changePercent',
                                t('folio.colChange'),
                                'right',
                                'folio-table__num',
                              )}
                              {renderSortHeader(
                                'totalReturnPct',
                                t('folio.colTotalPnl'),
                                'right',
                                'folio-table__num',
                              )}
                              <th className="folio-table__remove-head" aria-label={t('folio.colActions')} />
                            </tr>
                          </thead>
                          <tbody>
                            {displayRows.map((row) => {
                              const positive = row.changePercent >= 0;
                              const totalPositive = (row.totalReturnPct ?? 0) >= 0;
                              const sharesLocked = row.sharesLocked ?? false;
                              const openDateLocked = row.openDateLocked ?? false;
                              const costLocked = row.costLocked ?? false;
                              const effectiveOpenDate = row.openDate ?? portfolioOpenDate;
                              const localizedName = displayName(row);

                              return (
                                <tr key={row.ticker}>
                                  <td className="folio-table__ticker-cell">
                                    <button
                                      type="button"
                                      className="folio-table__ticker folio-table__ticker-link"
                                      title={t('entityPage.openTicker')}
                                      aria-label={`${t('entityPage.openTicker')}: ${row.ticker}`}
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
                                  <td className="folio-table__date-cell">
                                    <FolioLockableField
                                      locked={openDateLocked}
                                      lockHint={lockHint}
                                      unlockHint={unlockHint}
                                      onToggleLock={() =>
                                        onToggleOpenDateLock(row.ticker, !openDateLocked)
                                      }
                                    >
                                      <FolioHoldingOpenDatePicker
                                        value={effectiveOpenDate}
                                        floorDate={portfolioOpenDate}
                                        usesDefault={row.usesDefaultOpenDate ?? true}
                                        disabled={openDateLocked}
                                        onChange={(nextDate) => handleOpenDateChange(row, nextDate)}
                                      />
                                    </FolioLockableField>
                                  </td>
                                  <td className="folio-table__num folio-table__input-cell">
                                    <FolioLockableField
                                      locked={sharesLocked}
                                      lockHint={lockHint}
                                      unlockHint={unlockHint}
                                      onToggleLock={() =>
                                        onToggleSharesLock(row.ticker, !sharesLocked)
                                      }
                                    >
                                      <input
                                        type="number"
                                        min={0}
                                        step={sharesInputStep(row.market)}
                                        className="folio-table__shares-input"
                                        value={draftShares[row.ticker] ?? formatSharesForMarket(row.market, row.shares)}
                                        disabled={sharesLocked}
                                        onChange={(event) => {
                                          setDraftShares((prev) => ({
                                            ...prev,
                                            [row.ticker]: event.target.value,
                                          }));
                                        }}
                                        onBlur={() => applyShareForRow(row)}
                                      />
                                    </FolioLockableField>
                                  </td>
                                  <td className="folio-table__num">{row.weight.toFixed(1)}%</td>
                                  <td className="folio-table__num folio-table__input-cell">
                                    <FolioLockableField
                                      locked={costLocked}
                                      lockHint={lockHint}
                                      unlockHint={unlockHint}
                                      onToggleLock={() => onToggleCostLock(row.ticker, !costLocked)}
                                    >
                                      <input
                                        type="number"
                                        min={row.costLow ?? 0}
                                        max={row.costHigh ?? undefined}
                                        step={0.01}
                                        className={`folio-table__cost-input ${
                                          costErrors[row.ticker] ? 'folio-table__cost-input--error' : ''
                                        }`}
                                        value={draftCosts[row.ticker] ?? row.cost.toFixed(2)}
                                        disabled={costLocked}
                                        title={resolveCostInputTitle(row, costErrors[row.ticker], t)}
                                        onChange={(event) => {
                                          setDraftCosts((prev) => ({
                                            ...prev,
                                            [row.ticker]: event.target.value,
                                          }));
                                          setCostErrors((prev) => {
                                            const next = { ...prev };
                                            delete next[row.ticker];
                                            return next;
                                          });
                                        }}
                                        onBlur={() => applyCostForRow(row)}
                                      />
                                    </FolioLockableField>
                                  </td>
                                  <td className="folio-table__num folio-table__price">
                                    {formatStockPrice(row.price)}
                                  </td>
                                  <td
                                    className={`folio-table__num folio-table__change ${
                                      positive ? 'sphere-table__up' : 'sphere-table__down'
                                    }`}
                                  >
                                    {formatSignedPercent(row.changePercent)}
                                  </td>
                                  <td
                                    className={`folio-table__num folio-table__change ${
                                      totalPositive ? 'sphere-table__up' : 'sphere-table__down'
                                    }`}
                                  >
                                    {row.totalReturnPct == null
                                      ? '—'
                                      : formatSignedPercent(row.totalReturnPct)}
                                  </td>
                                  <td className="folio-table__remove-cell">
                                    <button
                                      type="button"
                                      className="folio-holdings__remove"
                                      aria-label={t('folio.removeHolding', { ticker: row.ticker })}
                                      disabled={removingTicker === row.ticker || addingTicker}
                                      onClick={() => onRemoveHolding(row.ticker, row.market)}
                                    >
                                      <TrashIcon />
                                    </button>
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <p className="folio-holdings__market-empty">{t('folio.noMarketHoldings')}</p>
                    )}
                  </section>
                );
              })}
            </div>
          )}
        </div>
    </>
  );

  if (embedded) {
    return (
      <div className="folio-holdings folio-holdings--embedded">
        {tableContent}
      </div>
    );
  }

  return (
    <aside className="folio-holdings">
      <article className="folio-card folio-holdings__table-card">
        <header className="folio-card__head">
          <h3 className="folio-card__title">{t('folio.holdingsTitle')}</h3>
        </header>
        {tableContent}
      </article>
    </aside>
  );
}
