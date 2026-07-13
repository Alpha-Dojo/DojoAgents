import { useState } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import type { AgentToolActivityItem } from '../../types/agent';
import type { AgentVizBlock } from '../../types/agentViz';
import { agentToolLabel } from '../../utils/agentToolLabels';
import {
  formatToolArguments,
  getExecuteCodeResultContent,
  getExecuteCodeSource,
} from '../../utils/agentToolDetail';
import { parseSessionOutputFilesFromToolData } from '../../utils/sessionOutputFiles';
import { localizeAgentVizBlocks } from '../../utils/agentVizI18n';
import doneIcon from '../../assets/svg/done.svg';
import errorIcon from '../../assets/svg/error.svg';
import { ChevronIcon } from '../Folio/FolioSidebarIcons';
import { AgentSessionOutputFile } from './AgentSessionOutputFile';
import { AgentVizBlockView } from './viz/AgentVizPanel';

function ToolStepDetails({
  code,
  blocks,
  expanded,
  resultContent,
  summary,
}: {
  code?: string | null;
  blocks: AgentVizBlock[];
  expanded: boolean;
  resultContent?: string | null;
  summary?: string | null;
}) {
  const { t, locale } = useTranslation();

  if (!expanded) return null;

  const localizedBlocks = localizeAgentVizBlocks(blocks, t, locale);

  return (
    <div className="dojo-agent-tool-activity__results">
      <div className="dojo-agent-tool-activity__results-body">
        {code ? (
          <div className="dojo-agent-tool-activity__code-panel">
            <p className="dojo-agent-tool-activity__code-head">
              {locale === 'zh' ? '生成的 Python 代码' : 'Generated Python code'}
            </p>
            <pre className="dojo-agent-tool-activity__code-block">
              <code>{code}</code>
            </pre>
          </div>
        ) : null}
        {summary ? (
          <p className="dojo-agent-tool-activity__detail dojo-agent-tool-activity__detail--result">
            {summary}
          </p>
        ) : null}
        {resultContent ? (
          <div className="dojo-agent-tool-activity__output-panel">
            <p className="dojo-agent-tool-activity__output-head">
              {locale === 'zh' ? '脚本执行结果' : 'Execution output'}
            </p>
            <pre className="dojo-agent-tool-activity__output-block">
              <code>{resultContent}</code>
            </pre>
          </div>
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
  sessionId?: string | null;
}

export function AgentToolStep({ item, sessionId = null }: AgentToolStepProps) {
  const { t, locale } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const uiLocale = locale === 'zh' ? 'zh' : 'en';
  const argDetail =
    item.arguments != null ? formatToolArguments(item.tool, item.arguments, uiLocale) : null;
  const codeSource = getExecuteCodeSource(item.tool, item.arguments);
  const resultContent = getExecuteCodeResultContent(item.tool, item.resultContent);
  const resultDetail = item.resultSummary ?? null;
  const vizBlocks = item.vizBlocks ?? [];
  const outputFiles =
    item.status === 'done' ? parseSessionOutputFilesFromToolData(item.tool, item.data) : [];
  const showInlineResult =
    Boolean(resultDetail) && vizBlocks.length === 0 && !codeSource && outputFiles.length === 0;
  const canExpandDetails =
    Boolean(codeSource) ||
    Boolean(resultContent) ||
    (item.status !== 'running' && (vizBlocks.length > 0 || Boolean(resultDetail)));
  const statusIcon =
    item.status === 'done' ? doneIcon : item.status === 'error' ? errorIcon : null;
  const expandTitle = expanded
    ? locale === 'zh'
      ? '收起代码和结果'
      : 'Hide code and results'
    : locale === 'zh'
      ? '查看代码和结果'
      : 'View code and results';

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
            aria-expanded={canExpandDetails ? expanded : undefined}
            disabled={!canExpandDetails}
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
            {canExpandDetails ? (
              <span
                className="dojo-agent-tool-activity__results-chevron"
                title={codeSource ? expandTitle : expanded ? t('agent.hideResults') : t('agent.viewResults')}
              >
                <ChevronIcon expanded={expanded} />
              </span>
            ) : null}
          </button>
          {argDetail ? <p className="dojo-agent-tool-activity__detail">{argDetail}</p> : null}
          {outputFiles.length > 0 && sessionId
            ? outputFiles.map((outputFile) => (
                <AgentSessionOutputFile
                  key={`${outputFile.filename}:${outputFile.path}`}
                  sessionId={sessionId}
                  filename={outputFile.filename}
                  path={outputFile.path}
                  bytesWritten={outputFile.bytes_written}
                />
              ))
            : null}
          {showInlineResult && item.status === 'done' ? (
            <p className="dojo-agent-tool-activity__detail dojo-agent-tool-activity__detail--result">
              {resultDetail}
            </p>
          ) : null}
        </div>
      </div>
      <ToolStepDetails
        code={codeSource}
        blocks={vizBlocks}
        expanded={expanded}
        resultContent={item.status === 'done' ? resultContent : null}
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
