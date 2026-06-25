import { useEffect, useState } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import type { AgentActivityStep } from '../../types/agent';
import { AgentEvalHints } from './AgentEvalHints';
import { AgentThinkStep } from './AgentThinking';
import { AgentToolStep } from './AgentToolActivity';

interface AgentActivityTimelineProps {
  steps: AgentActivityStep[];
  phase?: 'planning' | 'tools' | 'answering' | 'done' | null;
  streaming?: boolean;
  retryNotice?: string | null;
  onToggleThinkBlock: (blockId: string) => void;
}

export function AgentActivityTimeline({
  steps,
  phase = null,
  streaming = false,
  retryNotice = null,
  onToggleThinkBlock,
}: AgentActivityTimelineProps) {
  const { t } = useTranslation();
  const [phaseElapsedSec, setPhaseElapsedSec] = useState(0);

  useEffect(() => {
    if (!streaming || !phase) {
      setPhaseElapsedSec(0);
      return;
    }
    const startedAt = Date.now();
    setPhaseElapsedSec(0);
    const timer = window.setInterval(() => {
      setPhaseElapsedSec(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [phase, streaming]);

  if (steps.length === 0 && !phase && !retryNotice) {
    return null;
  }

  return (
    <div className="dojo-agent-timeline" aria-live="polite">
      {steps.map((step) => {
        if (step.kind === 'think') {
          return (
            <AgentThinkStep
              key={step.id}
              block={step.block}
              onToggle={() => onToggleThinkBlock(step.block.id)}
            />
          );
        }
        if (step.kind === 'eval') {
          return <AgentEvalHints key={step.id} issues={step.hint.issues} />;
        }
        return <AgentToolStep key={step.id} item={step.item} />;
      })}
      {streaming && retryNotice ? (
        <p className="dojo-agent-thinking__retry">{retryNotice}</p>
      ) : null}
      {streaming && phase ? (
        <p className={`dojo-agent-thinking__phase dojo-agent-thinking__phase--${phase}`}>
          {phase === 'planning'
            ? t('agent.phasePlanning')
            : phase === 'tools'
              ? t('agent.phaseTools')
              : phase === 'answering'
                ? t('agent.phaseAnswering')
                : t('agent.phaseDone')}
          {phaseElapsedSec >= 8 ? (
            <span className="dojo-agent-thinking__phase-elapsed">
              {' '}
              {t('agent.phaseElapsed', { seconds: phaseElapsedSec })}
            </span>
          ) : null}
        </p>
      ) : null}
    </div>
  );
}
