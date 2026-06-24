import { useTranslation } from '../../hooks/useTranslation';
import type { AgentPhase, AgentToolActivityItem } from '../../types/agent';

interface AgentToolActivityProps {
  items: AgentToolActivityItem[];
  thinking?: boolean;
  phase?: AgentPhase;
  retries?: string[];
  evalHints?: string[];
}

function toolLabel(name: string): string {
  return name
    .replace(/^portfolio_/, 'portfolio ')
    .replace(/^dojo_sdk_/, 'dojo sdk ')
    .replace(/_/g, ' ')
    .trim();
}

function phaseLabel(phase: AgentPhase | undefined, t: (key: string) => string): string {
  if (!phase) return t('agent.thinking');
  if (phase === 'planning') return t('agent.phasePlanning');
  if (phase === 'tools') return t('agent.phaseTools');
  return t('agent.phaseAnswering');
}

export function AgentToolActivity({
  items,
  thinking = false,
  phase,
  retries = [],
  evalHints = [],
}: AgentToolActivityProps) {
  const { t } = useTranslation();

  if (!thinking && items.length === 0 && retries.length === 0 && evalHints.length === 0 && !phase) {
    return null;
  }

  return (
    <div className="dojo-agent-tool-activity" aria-live="polite">
      {thinking || phase ? (
        <div className="dojo-agent-tool-activity__row dojo-agent-tool-activity__row--thinking">
          <span className="dojo-agent-tool-activity__spinner" aria-hidden />
          <span>{phaseLabel(phase, t)}</span>
        </div>
      ) : null}
      {retries.map((retry, index) => (
        <div key={`retry-${index}`} className="dojo-agent-tool-activity__row dojo-agent-tool-activity__row--thinking">
          <span className="dojo-agent-tool-activity__icon" aria-hidden>
            ↻
          </span>
          <span className="dojo-agent-tool-activity__label">{retry}</span>
        </div>
      ))}
      {evalHints.map((hint, index) => (
        <div key={`hint-${index}`} className="dojo-agent-tool-activity__row dojo-agent-tool-activity__row--error">
          <span className="dojo-agent-tool-activity__icon" aria-hidden>
            !
          </span>
          <span className="dojo-agent-tool-activity__label">{hint}</span>
        </div>
      ))}
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
                : item.latencyMs
                  ? `${t('agent.toolDone')} · ${item.latencyMs}ms`
                  : t('agent.toolDone')}
          </span>
          {item.result ? (
            <span className="dojo-agent-tool-activity__meta">{item.result}</span>
          ) : null}
        </div>
      ))}
    </div>
  );
}
