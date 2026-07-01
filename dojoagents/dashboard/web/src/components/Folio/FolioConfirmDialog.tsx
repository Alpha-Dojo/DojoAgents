import { useEffect, useRef, useState } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import { DojoButton } from '../ui';

interface FolioConfirmDialogProps {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm: () => Promise<void>;
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
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !submitting) onCancel();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onCancel, open, submitting]);

  useEffect(() => {
    if (open) dialogRef.current?.focus();
  }, [open]);

  const handleConfirm = async () => {
    if (submitting) return;
    setSubmitting(true);
    try {
      await onConfirm();
    } catch {
      // The mutation owner exposes the request error; keep this dialog open for retry.
    } finally {
      setSubmitting(false);
    }
  };

  if (!open) return null;

  return (
    <div className="folio-dialog" role="presentation">
      <button
        type="button"
        className="folio-dialog__backdrop"
        aria-label={cancelLabel ?? t('folio.cancel')}
        disabled={submitting}
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
          <DojoButton size="sm" variant="secondary" disabled={submitting} onClick={onCancel}>
            {cancelLabel ?? t('folio.cancel')}
          </DojoButton>
          <DojoButton
            size="sm"
            variant="error"
            disabled={submitting}
            onClick={() => void handleConfirm()}
          >
            {confirmLabel ?? t('folio.confirmDelete')}
          </DojoButton>
        </div>
      </div>
    </div>
  );
}
