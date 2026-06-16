import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import type { FolioPortfolioDetail } from '../../api/dojoFolio';
import type { MarketCode } from '../../types/dojoMesh';
import { DEFAULT_FOLIO_CONFIG, FOLIO_MARKETS } from '../../types/dojoFolio';
import { normalizeManualShares, sharesInputStep } from '../../utils/folioAllocation';
import { formatSignedPercent } from '../../utils/folioFormat';
import { FolioAddHoldingSearch } from './FolioAddHoldingSearch';
import { FolioHoldingOpenDatePicker } from './FolioHoldingOpenDatePicker';
import { FolioMarketLabel } from './FolioMarketLabel';

interface FolioHoldingsPanelProps {
  portfolio: FolioPortfolioDetail;
  loading?: boolean;
  addingTicker?: boolean;
  allocating?: boolean;
  onApplyShares: (
    sharesByTicker: Record<string, number>,
    manualSharesByTicker: Record<string, boolean>,
  ) => void;
  onApplyOpenDate: (ticker: string, openDate: string | null) => void;
  onAddHolding: (ticker: string, market: MarketCode) => void;
  onAutoAllocate: (market: MarketCode) => void;
}

export function FolioHoldingsPanel({
  portfolio,
  loading = false,
  addingTicker = false,
  allocating = false,
  onApplyShares,
  onApplyOpenDate,
  onAddHolding,
  onAutoAllocate,
}: FolioHoldingsPanelProps) {
  const { t } = useTranslation();
  const [draftShares, setDraftShares] = useState<Record<string, string>>({});
  const [manualTickers, setManualTickers] = useState<Set<string>>(new Set());

  const portfolioOpenDate = portfolio.config?.startDate ?? DEFAULT_FOLIO_CONFIG.startDate;
  const earliestDataDate = portfolio.performance?.dates?.[0] ?? null;

  useEffect(() => {
    const next: Record<string, string> = {};
    const manual = new Set<string>();
    for (const row of portfolio.holdings) {
      next[row.ticker] = String(row.shares);
      if (row.manualShares) manual.add(row.ticker);
    }
    setDraftShares(next);
    setManualTickers(manual);
  }, [portfolio.holdings, portfolio.id, portfolio.sharesByTicker]);

  const holdingsByMarket = useMemo(() => {
    const grouped: Record<MarketCode, FolioPortfolioDetail['holdings']> = {
      us: [],
      sh: [],
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
      sh: new Set(),
      hk: new Set(),
    };
    for (const row of portfolio.holdings) {
      grouped[row.market].add(row.ticker);
    }
    return grouped;
  }, [portfolio.holdings]);

  const sharesDirty = useMemo(() => {
    return portfolio.holdings.some((row) => {
      const draft = draftShares[row.ticker];
      if (draft == null) return false;
      const normalized = normalizeManualShares(row.market, Number(draft));
      return normalized !== row.shares;
    });
  }, [draftShares, portfolio.holdings]);

  const applyDraftShares = () => {
    const next: Record<string, number> = { ...portfolio.sharesByTicker };
    const manualSharesByTicker: Record<string, boolean> = {};
    for (const row of portfolio.holdings) {
      const draft = draftShares[row.ticker];
      if (draft == null) continue;
      const normalized = normalizeManualShares(row.market, Number(draft));
      if (normalized > 0) next[row.ticker] = normalized;
      else delete next[row.ticker];
      manualSharesByTicker[row.ticker] = manualTickers.has(row.ticker);
    }
    onApplyShares(next, manualSharesByTicker);
  };

  const handleOpenDateChange = (row: FolioPortfolioDetail['holdings'][number], nextDate: string) => {
    const usesPortfolioDefault = nextDate === portfolioOpenDate;
    onApplyOpenDate(row.ticker, usesPortfolioDefault ? null : nextDate);
  };

  const hasHoldings = portfolio.holdings.length > 0;

  return (
    <aside className="folio-holdings">
      <article className="folio-card folio-holdings__table-card">
        <header className="folio-card__head">
          <h3 className="folio-card__title">{t('folio.holdingsTitle')}</h3>
          {hasHoldings ? (
            <button
              type="button"
              className="folio-holdings__confirm"
              disabled={!sharesDirty}
              onClick={applyDraftShares}
            >
              {t('folio.confirmShares')}
            </button>
          ) : null}
        </header>

        <div className="folio-holdings__table-wrap">
          {loading ? (
            <p className="folio-holdings__empty">{t('folio.loading')}</p>
          ) : (
            <div className="folio-holdings__markets">
              {FOLIO_MARKETS.map((market) => {
                const rows = holdingsByMarket[market];
                return (
                  <section key={market} className={`folio-holdings__market folio-holdings__market--${market}`}>
                    <header className="folio-holdings__market-head">
                      <FolioMarketLabel market={market} />
                      {rows.length > 0 ? (
                        <button
                          type="button"
                          className="folio-holdings__auto-allocate"
                          disabled={allocating}
                          onClick={() => onAutoAllocate(market)}
                        >
                          {t('folio.autoAllocate')}
                        </button>
                      ) : null}
                    </header>

                    {rows.length > 0 ? (
                      <table className="folio-table folio-table--compact">
                        <thead>
                          <tr>
                            <th>{t('folio.colTicker')}</th>
                            <th>{t('folio.colName')}</th>
                            <th>{t('folio.colOpenDate')}</th>
                            <th className="folio-table__num">{t('folio.colShares')}</th>
                            <th className="folio-table__num">{t('folio.colWeight')}</th>
                            <th className="folio-table__num">{t('folio.colCost')}</th>
                            <th className="folio-table__num">{t('folio.colPrice')}</th>
                            <th className="folio-table__num">{t('folio.colChange')}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {rows.map((row) => {
                            const positive = row.changePercent >= 0;
                            const isManual = manualTickers.has(row.ticker);
                            const effectiveOpenDate = row.openDate ?? portfolioOpenDate;
                            return (
                              <tr key={row.ticker} className={isManual ? 'folio-table__row--manual' : undefined}>
                                <td>
                                  <span className="folio-table__ticker">{row.ticker}</span>
                                </td>
                                <td className="folio-table__name">{row.name}</td>
                                <td className="folio-table__date-cell">
                                  <FolioHoldingOpenDatePicker
                                    value={effectiveOpenDate}
                                    earliestDataDate={earliestDataDate}
                                    usesDefault={row.usesDefaultOpenDate ?? true}
                                    onChange={(nextDate) => handleOpenDateChange(row, nextDate)}
                                  />
                                </td>
                                <td className="folio-table__num">
                                  <input
                                    type="number"
                                    min={0}
                                    step={sharesInputStep(row.market)}
                                    className="folio-table__shares-input"
                                    value={draftShares[row.ticker] ?? String(row.shares)}
                                    onChange={(event) => {
                                      setDraftShares((prev) => ({
                                        ...prev,
                                        [row.ticker]: event.target.value,
                                      }));
                                      setManualTickers((prev) => new Set(prev).add(row.ticker));
                                    }}
                                  />
                                </td>
                                <td className="folio-table__num">{row.weight.toFixed(1)}%</td>
                                <td className="folio-table__num">{row.cost.toFixed(2)}</td>
                                <td className="folio-table__num">{row.price.toFixed(2)}</td>
                                <td className={`folio-table__num folio-tone--${positive ? 'up' : 'down'}`}>
                                  {formatSignedPercent(row.changePercent)}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    ) : (
                      <p className="folio-holdings__market-empty">{t('folio.noMarketHoldings')}</p>
                    )}

                    <FolioAddHoldingSearch
                      market={market}
                      existingTickers={existingTickersByMarket[market]}
                      adding={addingTicker}
                      onAdd={onAddHolding}
                    />
                  </section>
                );
              })}
            </div>
          )}
        </div>

        {sharesDirty ? (
          <p className="folio-holdings__pending">{t('folio.sharesPending')}</p>
        ) : null}
      </article>
    </aside>
  );
}
