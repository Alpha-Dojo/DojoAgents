import { useState, type MouseEvent } from 'react';
import { revealSessionInput } from '../../api/agent';
import { parseApiErrorMessage } from '../../api/http';
import { useTranslation } from '../../hooks/useTranslation';
import { formatBytesLabel } from '../../utils/sessionOutputFiles';
import { DojoButton } from '../ui';

interface AgentSessionInputFileProps {
  sessionId: string;
  filename: string;
  path: string;
  bytes?: number;
  variant?: 'card' | 'list' | 'chip';
}

export function AgentSessionInputFile({
  sessionId,
  filename,
  path,
  bytes,
  variant = 'list',
}: AgentSessionInputFileProps) {
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
      await revealSessionInput(sessionId, filename);
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

  const sizeLabel = typeof bytes === 'number' ? formatBytesLabel(bytes, uiLocale) : null;

  if (variant === 'chip') {
    return (
      <div className="dojo-agent-file-chip">
        <span className="dojo-agent-file-chip__name" title={path}>
          {filename}
        </span>
        {sizeLabel ? <span className="dojo-agent-file-chip__size">{sizeLabel}</span> : null}
        <button
          type="button"
          className="dojo-agent-file-chip__remove"
          aria-label={t('agent.removeFile')}
          onClick={(event) => event.stopPropagation()}
        >
          ×
        </button>
      </div>
    );
  }

  return (
    <div className={`dojo-agent-output-file dojo-agent-output-file--${variant}`}>
      <div className="dojo-agent-output-file__head">
        <span className="dojo-agent-output-file__icon" aria-hidden>
          📎
        </span>
        <div className="dojo-agent-output-file__meta">
          <span className="dojo-agent-output-file__filename" title={filename}>
            {filename}
          </span>
          {sizeLabel ? (
            <span className="dojo-agent-output-file__size">{sizeLabel}</span>
          ) : null}
        </div>
      </div>
      <button
        type="button"
        className="dojo-agent-output-file__path"
        title={t('agent.outputPathHint', { path })}
        onClick={handlePathClick}
      >
        {path}
      </button>
      <div className="dojo-agent-output-file__actions">
        <DojoButton size="xs" variant="secondary" onClick={() => void copyPath()}>
          {copied ? t('agent.pathCopied') : t('agent.copyPath')}
        </DojoButton>
        <DojoButton
          size="xs"
          variant="secondary"
          disabled={revealing}
          onClick={() => void reveal()}
        >
          {t('agent.revealInFolder')}
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
