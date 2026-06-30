import { useState } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import type { AgentToolActivityItem } from '../../types/agent';
import type { AgentVizBlock } from '../../types/agentViz';
import { agentToolLabel } from '../../utils/agentToolLabels';
import { formatToolArguments } from '../../utils/agentToolDetail';
import { localizeAgentVizBlocks } from '../../utils/agentVizI18n';
import doneIcon from '../../assets/svg/done.svg';
import errorIcon from '../../assets/svg/error.svg';
import { ChevronIcon } from '../Folio/FolioSidebarIcons';
import { AgentVizBlockView } from './viz/AgentVizPanel';

function ToolStepResults({
  blocks,
  expanded,
  summary,
}: {
  blocks: AgentVizBlock[];
  expanded: boolean;
  summary?: string | null;
}) {
  const { t, locale } = useTranslation();

  if (!expanded) return null;

  const localizedBlocks = localizeAgentVizBlocks(blocks, t, locale);

  return (
    <div className="dojo-agent-tool-activity__results">
      <div className="dojo-agent-tool-activity__results-body">
        {summary ? (
          <p className="dojo-agent-tool-activity__detail dojo-agent-tool-activity__detail--result">
            {summary}
          </p>
        ) : null}
        {localizedBlocks.map((block) => (
          <AgentVizBlockView key={block.id} block={block} />
        ))}
      </div>
    </div>
  );
}

interface AgentToolStepProps {
  item: AgentToolActivityItem;
}

export function AgentToolStep({ item }: AgentToolStepProps) {
  const { t, locale } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const uiLocale = locale === 'zh' ? 'zh' : 'en';
  const argDetail =
    item.arguments != null ? formatToolArguments(item.tool, item.arguments, uiLocale) : null;
  const resultDetail = item.resultSummary ?? null;
  const vizBlocks = item.vizBlocks ?? [];
  const showInlineResult = Boolean(resultDetail) && vizBlocks.length === 0;
  const canExpandResults =
    item.status !== 'running' && (vizBlocks.length > 0 || Boolean(resultDetail));
  const statusIcon =
    item.status === 'done' ? doneIcon : item.status === 'error' ? errorIcon : null;

  return (
    <div className={`dojo-agent-tool-activity__step dojo-agent-tool-activity__step--${item.status}`}>
      <div
        className={`dojo-agent-tool-activity__row dojo-agent-tool-activity__row--${item.status}`}
      >
        <span
          className={`dojo-agent-tool-activity__icon dojo-agent-tool-activity__icon--${item.status}`}
          style={
            statusIcon
              ? { WebkitMaskImage: `url("${statusIcon}")`, maskImage: `url("${statusIcon}")` }
              : undefined
          }
          aria-hidden
        />
        <div className="dojo-agent-tool-activity__main">
          <button
            type="button"
            className="dojo-agent-tool-activity__headline"
            aria-expanded={canExpandResults ? expanded : undefined}
            disabled={!canExpandResults}
            onClick={() => setExpanded((prev) => !prev)}
          >
            <div className="dojo-agent-tool-activity__headline-info">
              <span className="dojo-agent-tool-activity__label">
                {agentToolLabel(item.tool, uiLocale)}
              </span>
              {item.status === 'running' && (
                <span className="dojo-agent-tool-activity__meta">{t('agent.toolRunning')}</span>
              )}
              {item.status === 'done' && item.latencyMs != null && (
                <span className="dojo-agent-tool-activity__meta">
                  {t('agent.toolDone', { ms: Math.round(item.latencyMs) })}
                </span>
              )}
              {item.status === 'error' && item.error && (
                <span className="dojo-agent-tool-activity__meta dojo-agent-tool-activity__meta--error">
                  {item.error}
                </span>
              )}
            </div>
            {canExpandResults ? (
              <span
                className="dojo-agent-tool-activity__results-chevron"
                title={expanded ? t('agent.hideResults') : t('agent.viewResults')}
              >
                <ChevronIcon expanded={expanded} />
              </span>
            ) : null}
          </button>
          {argDetail ? <p className="dojo-agent-tool-activity__detail">{argDetail}</p> : null}
          {showInlineResult && item.status === 'done' ? (
            <p className="dojo-agent-tool-activity__detail dojo-agent-tool-activity__detail--result">
              {resultDetail}
            </p>
          ) : null}
        </div>
      </div>
      <ToolStepResults
        blocks={vizBlocks}
        expanded={expanded}
        summary={item.status === 'done' ? resultDetail : null}
      />
    </div>
  );
}

interface AgentToolActivityProps {
  items: AgentToolActivityItem[];
  thinking?: boolean;
}

/** @deprecated Prefer AgentActivityTimeline for chronological rendering. */
export function AgentToolActivity({ items, thinking = false }: AgentToolActivityProps) {
  const { t } = useTranslation();

  if (!thinking && items.length === 0) return null;

  return (
    <div className="dojo-agent-tool-activity" aria-live="polite">
      {thinking && (
        <div className="dojo-agent-tool-activity__row dojo-agent-tool-activity__row--thinking">
          <span className="dojo-agent-tool-activity__spinner" aria-hidden />
          <span>{t('agent.thinking')}</span>
        </div>
      )}
      {items.map((item, index) => (
        <AgentToolStep key={`${item.tool}-${index}`} item={item} />
      ))}
    </div>
  );
}
