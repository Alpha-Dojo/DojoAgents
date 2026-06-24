import { useEffect, useRef } from 'react';
import { useTranslation } from '../../hooks/useTranslation';

interface FolioConfirmDialogProps {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export function FolioConfirmDialog({
  open,
  title,
  message,
  confirmLabel,
  cancelLabel,
  onConfirm,
  onCancel,
}: FolioConfirmDialogProps) {
  const { t } = useTranslation();
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onCancel();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open, onCancel]);

  useEffect(() => {
    if (open) dialogRef.current?.focus();
  }, [open]);

  if (!open) return null;

  return (
    <div className="folio-dialog" role="presentation">
      <button
        type="button"
        className="folio-dialog__backdrop"
        aria-label={cancelLabel ?? t('folio.cancel')}
        onClick={onCancel}
      />
      <div
        ref={dialogRef}
        className="folio-dialog__panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="folio-dialog-title"
        tabIndex={-1}
      >
        <h3 id="folio-dialog-title" className="folio-dialog__title">
          {title}
        </h3>
        <p className="folio-dialog__message">{message}</p>
        <div className="folio-dialog__actions">
          <button type="button" className="folio-dialog__button folio-dialog__button--ghost" onClick={onCancel}>
            {cancelLabel ?? t('folio.cancel')}
          </button>
          <button
            type="button"
            className="folio-dialog__button folio-dialog__button--danger"
            onClick={onConfirm}
          >
            {confirmLabel ?? t('folio.confirmDelete')}
          </button>
        </div>
      </div>
    </div>
  );
}
