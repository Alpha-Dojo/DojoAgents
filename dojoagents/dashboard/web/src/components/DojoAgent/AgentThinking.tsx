import { useTranslation } from '../../hooks/useTranslation';
import type { AgentThinkBlock } from '../../types/agent';

interface AgentThinkStepProps {
  block: AgentThinkBlock;
  onToggle: () => void;
}

export function AgentThinkStep({ block, onToggle }: AgentThinkStepProps) {
  const { t } = useTranslation();

  return (
    <div
      className={`dojo-agent-thinking__block${
        block.done ? ' dojo-agent-thinking__block--done' : ' dojo-agent-thinking__block--live'
      }`}
    >
      <button
        type="button"
        className="dojo-agent-thinking__toggle"
        aria-expanded={!block.collapsed}
        onClick={onToggle}
      >
        <span className="dojo-agent-thinking__toggle-icon" aria-hidden>
          {block.collapsed ? '▸' : '▾'}
        </span>
        <span className="dojo-agent-thinking__toggle-label">
          {block.done ? t('agent.thinkDone') : t('agent.thinking')}
        </span>
        {!block.collapsed && block.done ? (
          <span className="dojo-agent-thinking__toggle-meta">
            {t('agent.thinkChars', { count: block.text.length })}
          </span>
        ) : null}
      </button>
      {!block.collapsed ? (
        <pre className="dojo-agent-thinking__body">{block.text || t('agent.thinking')}</pre>
      ) : null}
    </div>
  );
}

interface AgentThinkingProps {
  blocks: AgentThinkBlock[];
  phase?: 'planning' | 'tools' | 'answering' | 'done' | null;
  streaming?: boolean;
  retryNotice?: string | null;
  onToggleBlock: (id: string) => void;
}

/** @deprecated Prefer AgentActivityTimeline for chronological rendering. */
export function AgentThinking({
  blocks,
  phase = null,
  streaming = false,
  retryNotice = null,
  onToggleBlock,
}: AgentThinkingProps) {
  const { t } = useTranslation();

  if (blocks.length === 0 && !phase && !retryNotice) return null;

  return (
    <div className="dojo-agent-thinking" aria-live="polite">
      {retryNotice ? <p className="dojo-agent-thinking__retry">{retryNotice}</p> : null}
      {blocks.map((block) => (
        <AgentThinkStep key={block.id} block={block} onToggle={() => onToggleBlock(block.id)} />
      ))}
      {streaming && phase ? (
        <p className={`dojo-agent-thinking__phase dojo-agent-thinking__phase--${phase}`}>
          {phase === 'planning'
            ? t('agent.phasePlanning')
            : phase === 'tools'
              ? t('agent.phaseTools')
              : phase === 'answering'
                ? t('agent.phaseAnswering')
                : t('agent.phaseDone')}
        </p>
      ) : null}
    </div>
  );
}
