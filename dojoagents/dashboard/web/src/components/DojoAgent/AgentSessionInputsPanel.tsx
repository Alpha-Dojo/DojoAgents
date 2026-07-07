import { useTranslation } from '../../hooks/useTranslation';
import type { AgentSessionInputFile as AgentSessionInputFileItem } from '../../types/agent';
import { AgentSessionInputFile } from './AgentSessionInputFile';

interface AgentSessionInputsPanelProps {
  sessionId: string | null;
  files: AgentSessionInputFileItem[];
  loading: boolean;
  error: string | null;
}

export function AgentSessionInputsPanel({
  sessionId,
  files,
  loading,
  error,
}: AgentSessionInputsPanelProps) {
  const { t } = useTranslation();

  if (!sessionId) {
    return null;
  }

  return (
    <section className="dojo-agent-panel__outputs dojo-agent-panel__inputs" aria-label={t('agent.sessionInputs')}>
      <div className="dojo-agent-panel__outputs-head">
        <span className="dojo-agent-panel__outputs-label">{t('agent.sessionInputs')}</span>
        {files.length > 0 ? (
          <span className="dojo-agent-panel__outputs-count">{files.length}</span>
        ) : null}
      </div>
      {loading ? (
        <p className="dojo-agent-panel__outputs-status">{t('agent.sessionInputsLoading')}</p>
      ) : error ? (
        <p className="dojo-agent-panel__outputs-status dojo-agent-panel__outputs-status--error">
          {error}
        </p>
      ) : files.length === 0 ? (
        <p className="dojo-agent-panel__outputs-status">{t('agent.sessionInputsEmpty')}</p>
      ) : (
        <ul className="dojo-agent-panel__outputs-list">
          {files.map((file) => (
            <li key={file.filename}>
              <AgentSessionInputFile
                sessionId={sessionId}
                filename={file.filename}
                path={file.path}
                bytes={file.bytes}
                variant="list"
              />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
