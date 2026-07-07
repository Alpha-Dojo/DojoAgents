import { useState, type MouseEvent } from 'react';
import { revealSessionOutput } from '../../api/agent';
import { parseApiErrorMessage } from '../../api/http';
import { useTranslation } from '../../hooks/useTranslation';
import { formatBytesLabel } from '../../utils/sessionOutputFiles';
import { DojoButton } from '../ui';

interface AgentSessionOutputFileProps {
  sessionId: string;
  filename: string;
  path: string;
  bytesWritten?: number;
  variant?: 'card' | 'list';
}

export function AgentSessionOutputFile({
  sessionId,
  filename,
  path,
  bytesWritten,
  variant = 'card',
}: AgentSessionOutputFileProps) {
  const { locale, t } = useTranslation();
  const uiLocale = locale === 'zh' ? 'zh' : 'en';
  const [copied, setCopied] = useState(false);
  const [revealError, setRevealError] = useState<string | null>(null);
  const [revealing, setRevealing] = useState(false);

  const copyPath = async () => {
    try {
      await navigator.clipboard.writeText(path);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  const reveal = async () => {
    setRevealing(true);
    try {
      await revealSessionOutput(sessionId, filename);
      setRevealError(null);
    } catch (err) {
      setRevealError(parseApiErrorMessage(err, t('agent.revealFailed')));
    } finally {
      setRevealing(false);
    }
  };

  const handlePathClick = (event: MouseEvent<HTMLButtonElement>) => {
    if (event.metaKey || event.ctrlKey) {
      void reveal();
      return;
    }
    void copyPath();
  };

  const sizeLabel =
    typeof bytesWritten === 'number' ? formatBytesLabel(bytesWritten, uiLocale) : null;

  return (
    <div className={`dojo-agent-output-file dojo-agent-output-file--${variant}`}>
      <div className="dojo-agent-output-file__head">
        <span className="dojo-agent-output-file__icon" aria-hidden>
          📁
        </span>
        <div className="dojo-agent-output-file__meta">
          <div className="dojo-agent-output-file__title-row">
            <span className="dojo-agent-output-file__filename" title={filename}>
              {filename}
            </span>
            {sizeLabel ? (
              <span className="dojo-agent-output-file__size">({sizeLabel})</span>
            ) : null}
          </div>
          <button
            type="button"
            className="dojo-agent-output-file__path"
            title={t('agent.outputPathHint', { path })}
            onClick={handlePathClick}
          >
            {path}
          </button>
        </div>
      </div>
      <div className="dojo-agent-output-file__actions">
        <DojoButton
          icon={variant === 'list'}
          size="xs"
          variant="secondary"
          onClick={() => void copyPath()}
          title={copied ? t('agent.pathCopied') : t('agent.copyPath')}
        >
          {variant === 'list' ? (
            copied ? (
              <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
            ) : (
              <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
            )
          ) : (
            copied ? t('agent.pathCopied') : t('agent.copyPath')
          )}
        </DojoButton>
        <DojoButton
          icon={variant === 'list'}
          size="xs"
          variant="secondary"
          disabled={revealing}
          onClick={() => void reveal()}
          title={t('agent.revealInFolder')}
        >
          {variant === 'list' ? (
            <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
          ) : (
            t('agent.revealInFolder')
          )}
        </DojoButton>
      </div>
      {revealError ? (
        <p className="dojo-agent-output-file__error" role="alert">
          {revealError}
        </p>
      ) : null}
    </div>
  );
}
