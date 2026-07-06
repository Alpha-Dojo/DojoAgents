import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import type { AgentActivityStep } from '../../types/agent';
import { AgentEvalHints } from './AgentEvalHints';
import { AgentMarkdown } from './AgentMarkdown';
import { AgentThinkStep } from './AgentThinking';
import { AgentToolStep } from './AgentToolActivity';
import { agentToolLabel } from '../../utils/agentToolLabels';
import { getExecuteCodeSource } from '../../utils/agentToolDetail';
import { parseSessionOutputFileFromToolData } from '../../utils/sessionOutputFiles';

const REPEATED_TOOL_THRESHOLD = 3;

type TimelineEntry =
  | { kind: 'step'; step: AgentActivityStep }
  | { kind: 'tool-group'; steps: Extract<AgentActivityStep, { kind: 'tool' }>[] };

function isCompactableToolStep(step: AgentActivityStep): step is Extract<AgentActivityStep, { kind: 'tool' }> {
  if (step.kind !== 'tool' || step.item.status !== 'done' || step.item.error) {
    return false;
  }
  if (step.item.tool === 'write_session_file' || step.item.tool === 'execute_code' || step.item.tool === 'code_execution') {
    return false;
  }
  if (parseSessionOutputFileFromToolData(step.item.tool, step.item.data)) {
    return false;
  }
  return (
    !step.item.resultSummary &&
    (step.item.vizBlocks?.length ?? 0) === 0 &&
    !getExecuteCodeSource(step.item.tool, step.item.arguments)
  );
}

function buildTimelineEntries(steps: AgentActivityStep[]): TimelineEntry[] {
  const entries: TimelineEntry[] = [];
  for (let index = 0; index < steps.length; ) {
    const step = steps[index];
    if (!isCompactableToolStep(step)) {
      entries.push({ kind: 'step', step });
      index += 1;
      continue;
    }

    const group = [step];
    let nextIndex = index + 1;
    while (nextIndex < steps.length) {
      const candidate = steps[nextIndex];
      if (!isCompactableToolStep(candidate) || candidate.item.tool !== step.item.tool) {
        break;
      }
      group.push(candidate);
      nextIndex += 1;
    }

    if (group.length >= REPEATED_TOOL_THRESHOLD) {
      entries.push({ kind: 'tool-group', steps: group });
    } else {
      entries.push(
        ...group.map(
          (item): TimelineEntry => ({ kind: 'step', step: item }),
        ),
      );
    }
    index = nextIndex;
  }
  return entries;
}

function RepeatedToolGroup({
  steps,
  sessionId = null,
}: {
  steps: Extract<AgentActivityStep, { kind: 'tool' }>[];
  sessionId?: string | null;
}) {
  const { locale } = useTranslation();
  const uiLocale = locale === 'zh' ? 'zh' : 'en';
  const [expanded, setExpanded] = useState(false);
  const totalLatencyMs = steps.reduce((sum, step) => sum + (step.item.latencyMs ?? 0), 0);
  const label = agentToolLabel(steps[0]?.item.tool ?? '', uiLocale);
  const summary =
    uiLocale === 'zh'
      ? `${label} ×${steps.length} · ${Math.round(totalLatencyMs)}ms`
      : `${label} ×${steps.length} · ${Math.round(totalLatencyMs)}ms`;
  const toggleLabel =
    uiLocale === 'zh'
      ? expanded
        ? '收起重复调用'
        : '展开重复调用'
      : expanded
        ? 'Hide repeated calls'
        : 'Show repeated calls';

  return (
    <div className="dojo-agent-tool-activity__group">
      <button
        type="button"
        className="dojo-agent-tool-activity__group-toggle"
        aria-expanded={expanded}
        onClick={() => setExpanded((prev) => !prev)}
      >
        <span className="dojo-agent-tool-activity__group-summary">{summary}</span>
        <span className="dojo-agent-tool-activity__group-meta">{toggleLabel}</span>
      </button>
      {expanded ? (
        <div className="dojo-agent-tool-activity__group-body">
          {steps.map((step) => (
            <AgentToolStep key={step.id} item={step.item} sessionId={sessionId} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

interface AgentActivityTimelineProps {
  steps: AgentActivityStep[];
  phase?: 'planning' | 'tools' | 'answering' | 'done' | null;
  streaming?: boolean;
  retryNotice?: string | null;
  sessionId?: string | null;
  onToggleThinkBlock: (blockId: string) => void;
}

export function AgentActivityTimeline({
  steps,
  phase = null,
  streaming = false,
  retryNotice = null,
  sessionId = null,
  onToggleThinkBlock,
}: AgentActivityTimelineProps) {
  const { t } = useTranslation();
  const [phaseElapsedSec, setPhaseElapsedSec] = useState(0);
  const entries = useMemo(() => buildTimelineEntries(steps), [steps]);

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
      {entries.map((entry, index) => {
        if (entry.kind === 'tool-group') {
          return (
            <RepeatedToolGroup
              key={`tool-group-${entry.steps[0]?.id ?? index}`}
              steps={entry.steps}
              sessionId={sessionId}
            />
          );
        }
        const step = entry.step;
        if (step.kind === 'text') {
          if (!step.text) return null;
          return (
            <AgentMarkdown
              key={step.id}
              content={step.text}
              streaming={streaming && index === entries.length - 1}
            />
          );
        }
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
        return <AgentToolStep key={step.id} item={step.item} sessionId={sessionId} />;
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
