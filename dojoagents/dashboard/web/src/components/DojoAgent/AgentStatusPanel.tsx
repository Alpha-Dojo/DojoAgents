import { useEffect, useState } from "react";
import { fetchAgentSessionTokenStatus } from "../../api/agent";
import { ApiError } from "../../api/http";
import { useTranslation } from "../../hooks/useTranslation";
import type { AgentSessionTokenStatus } from "../../types/agent";

interface AgentStatusPanelProps {
  sessionId: string | null;
  refreshKey: number;
  onClose: () => void;
}

const tokenFormatter = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 });

function formatTokens(value: number): string {
  return tokenFormatter.format(Math.max(0, value));
}

export function AgentStatusPanel({ sessionId, refreshKey, onClose }: AgentStatusPanelProps) {
  const { t } = useTranslation();
  const [status, setStatus] = useState<AgentSessionTokenStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [unavailable, setUnavailable] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setStatus(null);
    setError(null);
    setUnavailable(!sessionId);
    if (!sessionId) return;

    setLoading(true);
    setUnavailable(false);
    void fetchAgentSessionTokenStatus(sessionId)
      .then((payload) => {
        if (!cancelled) setStatus(payload);
      })
      .catch((reason: unknown) => {
        if (cancelled) return;
        if (reason instanceof ApiError && reason.status === 404) {
          setUnavailable(true);
          return;
        }
        setError(reason instanceof Error ? reason.message : t("agent.statusLoadFailed"));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [refreshKey, sessionId, t]);

  const maxTokens = status?.session_max_tokens ?? 0;
  const usedTokens = status?.last_prompt_tokens ?? 0;
  const thresholdRatio = status?.compression_threshold_ratio ?? 0;
  const utilization = Math.max(0, Math.min(status?.utilization_ratio ?? 0, 1));
  const thresholdTokens = Math.round(maxTokens * thresholdRatio);
  const remainingToCompression = Math.max(0, thresholdTokens - usedTokens);
  const nearingCompression = thresholdTokens > 0 && usedTokens / thresholdTokens >= 0.9;

  return (
    <section
      className={`dojo-agent-status${nearingCompression ? " dojo-agent-status--warning" : ""}`}
      aria-label={t("agent.statusTitle")}
      aria-live="polite"
    >
      <div className="dojo-agent-status__head">
        <strong>{t("agent.statusTitle")}</strong>
        <button type="button" onClick={onClose} aria-label={t("agent.statusClose")}>
          {t("agent.statusClose")}
        </button>
      </div>
      {loading ? <p className="dojo-agent-status__notice">{t("agent.statusLoading")}</p> : null}
      {!loading && unavailable ? (
        <p className="dojo-agent-status__notice">{t("agent.statusUnavailable")}</p>
      ) : null}
      {!loading && error ? <p className="dojo-agent-status__error">{error}</p> : null}
      {!loading && status ? (
        <>
          <dl className="dojo-agent-status__summary">
            <div>
              <dt>{t("agent.statusSession")}</dt>
              <dd title={sessionId ?? ""}>{sessionId}</dd>
            </div>
            <div>
              <dt>{t("agent.statusContext")}</dt>
              <dd>
                {formatTokens(usedTokens)} / {formatTokens(maxTokens)}
                <span>{Math.round(utilization * 100)}%</span>
              </dd>
            </div>
          </dl>
          <div className="dojo-agent-status__meter" aria-label={t("agent.statusUtilization")}>
            <span style={{ width: `${utilization * 100}%` }} />
            <i style={{ left: `${Math.max(0, Math.min(thresholdRatio, 1)) * 100}%` }} />
          </div>
          <div className="dojo-agent-status__meter-meta">
            <span>{t("agent.statusCompressionAt", { percent: Math.round(thresholdRatio * 100) })}</span>
            <span>{t("agent.statusRemaining", { count: formatTokens(remainingToCompression) })}</span>
          </div>
          <dl className="dojo-agent-status__details">
            <div><dt>{t("agent.statusLastCall")}</dt><dd>{formatTokens(status.last_total_tokens)}</dd></div>
            <div><dt>{t("agent.statusLastOutput")}</dt><dd>{formatTokens(status.last_completion_tokens)}</dd></div>
            <div><dt>{t("agent.statusCumulative")}</dt><dd>{formatTokens(status.cumulative_total_tokens)}</dd></div>
            <div><dt>{t("agent.statusLoops")}</dt><dd>{status.loop_count}</dd></div>
            <div><dt>{t("agent.statusCompressions")}</dt><dd>{status.compression_count}</dd></div>
          </dl>
        </>
      ) : null}
    </section>
  );
}
