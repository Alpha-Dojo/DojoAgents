import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { createFolioOrder, createFolioPortfolio, fetchFolioPortfolios } from '../../api/folio';
import { publishFolioPortfolioUpdate } from '../../navigation/folio_sync';
import { useTranslation } from '../../hooks/useTranslation';
import type { FolioOrderDraftContext } from '../../types/folio';
import type { MarketCode } from '../../types/market';
import { FolioCreateOrderModal } from '../Folio/FolioCreateOrderModal';
import { LoadingIndicator } from '../ui/LoadingIndicator';

interface EntityCreateOrderButtonProps {
  ticker: string;
  market: MarketCode;
  name: string;
}

interface PortfolioRow {
  id: string;
  name: string;
}

function suggestPortfolioName(existing: string[]): string {
  const taken = new Set(existing);
  for (let index = 0; index < 1000; index += 1) {
    const candidate = `组合 ${String.fromCharCode(65 + (index % 26))}${index >= 26 ? index - 25 : ''}`;
    if (!taken.has(candidate)) return candidate;
  }
  return `组合 ${Date.now()}`;
}

export function EntityCreateOrderButton({ ticker, market, name }: EntityCreateOrderButtonProps) {
  const { t } = useTranslation();
  const listId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [placing, setPlacing] = useState(false);
  const [portfolios, setPortfolios] = useState<PortfolioRow[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [createName, setCreateName] = useState('');
  const [orderOpen, setOrderOpen] = useState(false);
  const [status, setStatus] = useState<{ tone: 'ok' | 'err'; text: string } | null>(null);
  const [panelPos, setPanelPos] = useState<{ top: number; left: number } | null>(null);

  const orderContext: FolioOrderDraftContext | null =
    orderOpen && selectedId
      ? { market, ticker, name }
      : null;

  const loadPortfolios = async () => {
    setLoading(true);
    try {
      const rows = await fetchFolioPortfolios();
      const mapped = rows.map((row) => ({ id: row.id, name: row.name }));
      setPortfolios(mapped);
      setCreateName(suggestPortfolioName(mapped.map((row) => row.name)));
      setSelectedId(mapped[0]?.id ?? null);
    } catch {
      setPortfolios([]);
      setSelectedId(null);
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
  }, [open]);

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

  const openOrderModal = (portfolioId: string) => {
    setSelectedId(portfolioId);
    setOrderOpen(true);
    setOpen(false);
  };

  const handleCreatePortfolioAndTrade = async () => {
    const portfolioName = createName.trim() || suggestPortfolioName(portfolios.map((row) => row.name));
    setPlacing(true);
    setStatus(null);
    try {
      const created = await createFolioPortfolio(portfolioName);
      openOrderModal(created.id);
    } catch {
      setStatus({ tone: 'err', text: t('folio.entityCreateOrderFailed') });
    } finally {
      setPlacing(false);
    }
  };

  const handleOpenOrderModal = () => {
    if (!selectedId) return;
    openOrderModal(selectedId);
  };

  const handleSubmitOrder = async (payload: Parameters<typeof createFolioOrder>[1]) => {
    if (!selectedId) return;
    setPlacing(true);
    try {
      const updated = await createFolioOrder(selectedId, payload);
      publishFolioPortfolioUpdate(updated);
      setStatus({ tone: 'ok', text: t('folio.entityCreateOrderSuccess') });
      setOrderOpen(false);
    } finally {
      setPlacing(false);
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
            aria-label={t('folio.entityCreateOrder')}
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
                  className="core-add-folio__create-btn core-add-folio__create-btn--order"
                  disabled={placing}
                  onClick={() => void handleCreatePortfolioAndTrade()}
                >
                  {t('folio.entityCreateOrderContinue')}
                </button>
              </div>
            </section>

            {loading ? (
              <LoadingIndicator
                className="core-add-folio__empty"
                label={t('folio.loading')}
                variant="panel"
              />
            ) : portfolios.length === 0 ? (
              <p className="core-add-folio__empty">{t('folio.entityCreateOrderEmptyHint')}</p>
            ) : (
              <>
                <p className="core-add-folio__section-label">{t('folio.entityCreateOrderPick')}</p>
                <ul className="core-add-folio__list" role="radiogroup" aria-label={t('folio.entityCreateOrderPick')}>
                  {portfolios.map((portfolio) => (
                    <li key={portfolio.id}>
                      <label className="core-add-folio__row core-add-folio__row--radio">
                        <input
                          type="radio"
                          className="core-add-folio__radio"
                          name={`entity-create-order-${listId}`}
                          checked={selectedId === portfolio.id}
                          disabled={placing}
                          onChange={() => setSelectedId(portfolio.id)}
                        />
                        <span className="core-add-folio__row-name">{portfolio.name}</span>
                      </label>
                    </li>
                  ))}
                </ul>
                <footer className="core-add-folio__foot">
                  <button
                    type="button"
                    className="core-add-folio__confirm core-add-folio__confirm--order"
                    disabled={placing || !selectedId}
                    onClick={handleOpenOrderModal}
                  >
                    {t('folio.entityCreateOrderContinue')}
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
        className="core-add-folio__trigger core-add-folio__trigger--order"
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-controls={open ? listId : undefined}
        onClick={(event) => {
          event.stopPropagation();
          setOpen((prev) => !prev);
          setStatus(null);
        }}
      >
        {t('folio.entityCreateOrder')}
      </button>

      {status && !open && !orderOpen ? (
        <span
          className={`core-add-folio__status core-add-folio__status--${status.tone === 'ok' ? 'ok' : 'err'}`}
        >
          {status.text}
        </span>
      ) : null}

      {panel}

      <FolioCreateOrderModal
        open={orderOpen}
        portfolioId={selectedId ?? ''}
        context={orderContext}
        placing={placing}
        onClose={() => setOrderOpen(false)}
        onSubmit={handleSubmitOrder}
      />
    </div>
  );
}
