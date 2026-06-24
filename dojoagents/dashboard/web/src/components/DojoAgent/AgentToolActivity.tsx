import { useTranslation } from '../../hooks/useTranslation';
import type { AgentToolActivityItem } from '../../types/agent';

interface AgentToolActivityProps {
  items: AgentToolActivityItem[];
  thinking?: boolean;
}

function toolLabel(name: string): string {
  return name
    .replace(/^portfolio_/, 'portfolio ')
    .replace(/^dojo_sdk_/, 'dojo sdk ')
    .replace(/_/g, ' ')
    .trim();
}

export function AgentToolActivity({ items, thinking = false }: AgentToolActivityProps) {
  const { t } = useTranslation();

  if (!thinking && items.length === 0) return null;

  return (
    <div className="dojo-agent-tool-activity" aria-live="polite">
      {thinking ? (
        <div className="dojo-agent-tool-activity__row dojo-agent-tool-activity__row--thinking">
          <span className="dojo-agent-tool-activity__spinner" aria-hidden />
          <span>{t('agent.thinking')}</span>
        </div>
      ) : null}
      {items.map((item, index) => (
        <div
          key={`${item.id}-${index}`}
          className={`dojo-agent-tool-activity__row dojo-agent-tool-activity__row--${item.status}`}
        >
          <span className="dojo-agent-tool-activity__icon" aria-hidden>
            {item.status === 'running' ? '◌' : item.status === 'error' ? '✕' : '✓'}
          </span>
          <span className="dojo-agent-tool-activity__label">{toolLabel(item.tool)}</span>
          <span className="dojo-agent-tool-activity__meta">
            {item.status === 'running'
              ? t('agent.toolRunning')
              : item.status === 'error'
                ? item.error || t('agent.toolFailed')
                : t('agent.toolDone')}
          </span>
        </div>
      ))}
    </div>
  );
}
