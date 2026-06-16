import { useEffect, useId, useRef, useState } from 'react';
import { addFolioHolding, fetchFolioPortfolios } from '../../api/dojoFolio';
import { useTranslation } from '../../hooks/useTranslation';
import type { MarketCode } from '../../types/dojoMesh';

interface CoreAddToFolioButtonProps {
  ticker: string;
  market: MarketCode;
}

export function CoreAddToFolioButton({ ticker, market }: CoreAddToFolioButtonProps) {
  const { t } = useTranslation();
  const listId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [submittingId, setSubmittingId] = useState<string | null>(null);
  const [portfolios, setPortfolios] = useState<Array<{ id: string; name: string }>>([]);
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    fetchFolioPortfolios()
      .then((rows) => {
        if (cancelled) return;
        setPortfolios(rows.map((row) => ({ id: row.id, name: row.name })));
      })
      .catch(() => {
        if (!cancelled) setPortfolios([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onPointerDown);
    return () => document.removeEventListener('mousedown', onPointerDown);
  }, [open]);

  const handleAdd = async (portfolioId: string) => {
    setSubmittingId(portfolioId);
    setStatus(null);
    try {
      await addFolioHolding(portfolioId, { ticker, market });
      const portfolio = portfolios.find((item) => item.id === portfolioId);
      setStatus(t('folio.addToPortfolioSuccess', { name: portfolio?.name ?? '' }));
      setOpen(false);
    } catch {
      setStatus(t('folio.addToPortfolioFailed'));
    } finally {
      setSubmittingId(null);
    }
  };

  return (
    <div className="core-add-folio" ref={rootRef}>
      <button
        type="button"
        className="core-add-folio__trigger"
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-controls={open ? listId : undefined}
        onClick={() => setOpen((prev) => !prev)}
      >
        {t('folio.addToPortfolio')}
      </button>

      {status ? <span className="core-add-folio__status">{status}</span> : null}

      {open ? (
        <div className="core-add-folio__panel">
          <p className="core-add-folio__title">{t('folio.addToPortfolioPick')}</p>
          <ul id={listId} className="core-add-folio__list" role="listbox">
            {loading ? <li className="core-add-folio__status">{t('folio.loading')}</li> : null}
            {!loading && portfolios.length === 0 ? (
              <li className="core-add-folio__status">{t('folio.noPortfolios')}</li>
            ) : null}
            {!loading
              ? portfolios.map((portfolio) => (
                  <li key={portfolio.id}>
                    <button
                      type="button"
                      className="core-add-folio__option"
                      role="option"
                      disabled={submittingId === portfolio.id}
                      onClick={() => handleAdd(portfolio.id)}
                    >
                      {portfolio.name}
                    </button>
                  </li>
                ))
              : null}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
