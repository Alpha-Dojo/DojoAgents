import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  addFolioHolding,
  createFolioPortfolio,
  fetchFolioPortfolioDetail,
  fetchFolioPortfolios,
  type FolioPortfolioDetail,
} from '../../api/folio';
import { publishFolioPortfolioUpdate } from '../../navigation/folio_sync';
import { cacheKeys } from '../../cache/cacheKeys';
import { fetchCached, getCached } from '../../cache/queryCache';
import { useTranslation } from '../../hooks/useTranslation';
import type { MarketCode } from '../../types/market';
import { tickersMatch } from '../../utils/tickerMatch';

interface EntityAddToFolioButtonProps {
  ticker: string;
  market: MarketCode;
}

interface PortfolioRow {
  id: string;
  name: string;
  hasTicker: boolean;
}

function suggestPortfolioName(existing: string[]): string {
  const taken = new Set(existing);
  for (let index = 0; index < 1000; index += 1) {
    const candidate = `组合 ${String.fromCharCode(65 + (index % 26))}${index >= 26 ? index - 25 : ''}`;
    if (!taken.has(candidate)) return candidate;
  }
  return `组合 ${Date.now()}`;
}

export function EntityAddToFolioButton({ ticker, market }: EntityAddToFolioButtonProps) {
  const { t } = useTranslation();
  const listId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [portfolios, setPortfolios] = useState<PortfolioRow[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [createName, setCreateName] = useState('');
  const [status, setStatus] = useState<{ tone: 'ok' | 'err'; text: string } | null>(null);
  const [panelPos, setPanelPos] = useState<{ top: number; left: number } | null>(null);

  const loadPortfolios = async () => {
    setLoading(true);
    try {
      const rows = await fetchFolioPortfolios();
      const enriched = await Promise.all(
        rows.map(async (row) => {
          try {
            const cacheKey = cacheKeys.folioPortfolioLite(row.id);
            const cached = getCached<FolioPortfolioDetail>(cacheKey);
            const detail =
              cached ??
              (await fetchCached(cacheKey, () =>
                fetchFolioPortfolioDetail(row.id, { includePerformance: false }),
              ));
            const hasTicker = detail.holdings.some(
              (holding) => tickersMatch(market, holding.ticker, ticker) && holding.market === market,
            );
            return { id: row.id, name: row.name, hasTicker };
          } catch {
            return { id: row.id, name: row.name, hasTicker: false };
          }
        }),
      );
      setPortfolios(enriched);
      setCreateName(suggestPortfolioName(enriched.map((row) => row.name)));
      setSelectedIds(new Set());
    } catch {
      setPortfolios([]);
      setCreateName(suggestPortfolioName([]));
    } finally {
      setLoading(false);
    }
  };

  const updatePanelPosition = () => {
    const trigger = triggerRef.current;
    if (!trigger) return;
    const rect = trigger.getBoundingClientRect();
    const panelWidth = 272;
    const left = Math.max(8, Math.min(rect.right - panelWidth, window.innerWidth - panelWidth - 8));
    setPanelPos({ top: rect.bottom + 6, left });
  };

  useEffect(() => {
    if (!open) return;
    void loadPortfolios();
  }, [open, ticker, market]);

  useLayoutEffect(() => {
    if (!open) {
      setPanelPos(null);
      return;
    }
    updatePanelPosition();
    window.addEventListener('resize', updatePanelPosition);
    window.addEventListener('scroll', updatePanelPosition, true);
    return () => {
      window.removeEventListener('resize', updatePanelPosition);
      window.removeEventListener('scroll', updatePanelPosition, true);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (rootRef.current?.contains(target) || panelRef.current?.contains(target)) return;
      setOpen(false);
    };
    document.addEventListener('mousedown', onPointerDown);
    return () => document.removeEventListener('mousedown', onPointerDown);
  }, [open]);

  const togglePortfolio = (portfolioId: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(portfolioId)) next.delete(portfolioId);
      else next.add(portfolioId);
      return next;
    });
  };

  const handleCreateAndAdd = async () => {
    const name = createName.trim() || suggestPortfolioName(portfolios.map((row) => row.name));
    setSubmitting(true);
    setStatus(null);
    try {
      const created = await createFolioPortfolio(name);
      const updated = await addFolioHolding(created.id, { ticker, market });
      publishFolioPortfolioUpdate(updated);
      setStatus({ tone: 'ok', text: t('folio.addToPortfolioCreateSuccess', { name: created.name }) });
      setOpen(false);
    } catch {
      setStatus({ tone: 'err', text: t('folio.addToPortfolioFailed') });
    } finally {
      setSubmitting(false);
    }
  };

  const handleConfirmAdd = async () => {
    if (selectedIds.size === 0) return;
    setSubmitting(true);
    setStatus(null);
    try {
      const ids = [...selectedIds];
      const results = await Promise.allSettled(
        ids.map((id) => addFolioHolding(id, { ticker, market })),
      );
      for (const result of results) {
        if (result.status === 'fulfilled') {
          publishFolioPortfolioUpdate(result.value);
        }
      }
      const succeeded = results.filter((result) => result.status === 'fulfilled').length;
      if (succeeded === 0) {
        setStatus({ tone: 'err', text: t('folio.addToPortfolioFailed') });
        return;
      }
      setStatus({
        tone: 'ok',
        text: t('folio.addToPortfolioMultiSuccess', { count: succeeded }),
      });
      setOpen(false);
    } catch {
      setStatus({ tone: 'err', text: t('folio.addToPortfolioFailed') });
    } finally {
      setSubmitting(false);
    }
  };

  const panel =
    open && panelPos
      ? createPortal(
          <div
            id={listId}
            ref={panelRef}
            className="core-add-folio__panel"
            role="dialog"
            aria-label={t('folio.addToPortfolio')}
            style={{ top: panelPos.top, left: panelPos.left }}
          >
            <section className="core-add-folio__create">
              <label className="core-add-folio__create-label">{t('folio.addToPortfolioCreate')}</label>
              <div className="core-add-folio__create-row">
                <input
                  type="text"
                  className="core-add-folio__create-input"
                  value={createName}
                  placeholder={t('folio.newPortfolio')}
                  onChange={(event) => setCreateName(event.target.value)}
                />
                <button
                  type="button"
                  className="core-add-folio__create-btn"
                  disabled={submitting}
                  onClick={() => void handleCreateAndAdd()}
                >
                  {t('folio.addToPortfolioCreateAndAdd')}
                </button>
              </div>
            </section>

            {loading ? (
              <p className="core-add-folio__empty">{t('folio.loading')}</p>
            ) : portfolios.length === 0 ? (
              <p className="core-add-folio__empty">{t('folio.addToPortfolioEmptyHint')}</p>
            ) : (
              <>
                <p className="core-add-folio__section-label">{t('folio.addToPortfolioPick')}</p>
                <ul className="core-add-folio__list">
                  {portfolios.map((portfolio) => {
                    const checked = selectedIds.has(portfolio.id);
                    return (
                      <li key={portfolio.id}>
                        <label
                          className={`core-add-folio__row${portfolio.hasTicker ? ' core-add-folio__row--held' : ''}`}
                        >
                          <input
                            type="checkbox"
                            className="core-add-folio__checkbox"
                            checked={checked}
                            disabled={portfolio.hasTicker || submitting}
                            onChange={() => togglePortfolio(portfolio.id)}
                          />
                          <span className="core-add-folio__row-name">{portfolio.name}</span>
                          {portfolio.hasTicker ? (
                            <span className="core-add-folio__row-badge">{t('folio.alreadyInPortfolio')}</span>
                          ) : null}
                        </label>
                      </li>
                    );
                  })}
                </ul>

                <footer className="core-add-folio__foot">
                  <span className="core-add-folio__selected">
                    {t('folio.addToPortfolioSelected', { count: selectedIds.size })}
                  </span>
                  <button
                    type="button"
                    className="core-add-folio__confirm"
                    disabled={submitting || selectedIds.size === 0}
                    onClick={() => void handleConfirmAdd()}
                  >
                    {t('folio.addToPortfolioConfirm')}
                  </button>
                </footer>
              </>
            )}
          </div>,
          document.body,
        )
      : null;

  return (
    <div className="core-add-folio" ref={rootRef}>
      <button
        ref={triggerRef}
        type="button"
        className="core-add-folio__trigger"
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-controls={open ? listId : undefined}
        onClick={(event) => {
          event.stopPropagation();
          setOpen((prev) => !prev);
          setStatus(null);
        }}
      >
        {t('folio.addToPortfolio')}
      </button>

      {status && !open ? (
        <span
          className={`core-add-folio__status core-add-folio__status--${status.tone === 'ok' ? 'ok' : 'err'}`}
        >
          {status.text}
        </span>
      ) : null}

      {panel}
    </div>
  );
}
