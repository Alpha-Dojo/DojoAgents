import { useEffect, useRef, useState } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import { DojoButton } from '../ui';

export function AddMarketSlot() {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open]);

  useEffect(() => {
    if (open) dialogRef.current?.focus();
  }, [open]);

  return (
    <>
      <button
        type="button"
        className="mesh-market-add"
        aria-label={t('marketPage.addMarketAria')}
        title={t('marketPage.addMarket')}
        onClick={() => setOpen(true)}
      >
        +
      </button>

      {open && (
        <div className="mesh-add-market-dialog" role="presentation">
          <button
            type="button"
            className="mesh-add-market-dialog__backdrop"
            aria-label={t('marketPage.comingSoonDismiss')}
            onClick={() => setOpen(false)}
          />
          <div
            ref={dialogRef}
            className="mesh-add-market-dialog__panel"
            role="dialog"
            aria-modal="true"
            aria-labelledby="mesh-add-market-title"
            tabIndex={-1}
          >
            <h3 id="mesh-add-market-title" className="mesh-add-market-dialog__title">
              {t('marketPage.comingSoonTitle')}
            </h3>
            <p className="mesh-add-market-dialog__body">{t('marketPage.comingSoonBody')}</p>
            <DojoButton
              variant="secondary"
              size="sm"
              className="mesh-add-market-dialog__action"
              aria-label={t("marketPage.comingSoonDismiss")}
              onClick={() => setOpen(false)}
            >
              {t('marketPage.comingSoonDismiss')}
            </DojoButton>
          </div>
        </div>
      )}
    </>
  );
}
