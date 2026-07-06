import { useTranslation } from '../../hooks/useTranslation';
import type { AgentSessionOutputFile as AgentSessionOutputFileItem } from '../../types/agent';
import { AgentSessionOutputFile } from './AgentSessionOutputFile';

interface AgentSessionOutputsPanelProps {
  sessionId: string | null;
  files: AgentSessionOutputFileItem[];
  loading: boolean;
  error: string | null;
}

export function AgentSessionOutputsPanel({
  sessionId,
  files,
  loading,
  error,
}: AgentSessionOutputsPanelProps) {
  const { t } = useTranslation();

  if (!sessionId) {
    return null;
  }

  return (
    <section className="dojo-agent-panel__outputs" aria-label={t('agent.sessionOutputs')}>
      <div className="dojo-agent-panel__outputs-head">
        <span className="dojo-agent-panel__outputs-label">{t('agent.sessionOutputs')}</span>
        {files.length > 0 ? (
          <span className="dojo-agent-panel__outputs-count">{files.length}</span>
        ) : null}
      </div>
      {loading ? (
        <p className="dojo-agent-panel__outputs-status">{t('agent.sessionOutputsLoading')}</p>
      ) : error ? (
        <p className="dojo-agent-panel__outputs-status dojo-agent-panel__outputs-status--error">
          {error}
        </p>
      ) : files.length === 0 ? (
        <p className="dojo-agent-panel__outputs-status">{t('agent.sessionOutputsEmpty')}</p>
      ) : (
        <ul className="dojo-agent-panel__outputs-list">
          {files.map((file) => (
            <li key={file.filename}>
              <AgentSessionOutputFile
                sessionId={sessionId}
                filename={file.filename}
                path={file.path}
                bytesWritten={file.bytes_written}
                variant="list"
              />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
