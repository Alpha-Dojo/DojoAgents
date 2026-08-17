import { useEffect, useState } from "react";
import { fetchAgentSessionUsage } from "../../api/agent";
import { ApiError } from "../../api/http";
import { useTranslation } from "../../hooks/useTranslation";
import type {
  AgentContextUsageSnapshot,
  AgentContextUsageCategory,
  AgentSessionUsage,
} from "../../types/agent";

interface AgentStatusPanelProps {
  sessionId: string | null;
  refreshKey: number;
  liveContext?: AgentContextUsageSnapshot | null;
  onClose: () => void;
}

const tokenFormatter = new Intl.NumberFormat(undefined, {
  maximumFractionDigits: 0,
});

const categoryColors: Record<AgentContextUsageCategory, string> = {
  system_prompt: "#9ca3af",
  tool_definitions: "#a78bfa",
  rules: "#34d399",
  skills: "#fbbf24",
  subagent_definitions: "#60a5fa",
  conversation: "#365463",
  memory: "#f472b6",
  attachments: "#fb923c",
  protocol_overhead: "#94a3b8",
  other: "#64748b",
};

const categoryLabelKeys: Record<AgentContextUsageCategory, string> = {
  system_prompt: "agent.contextCategorySystem",
  tool_definitions: "agent.contextCategoryTools",
  rules: "agent.contextCategoryRules",
  skills: "agent.contextCategorySkills",
  subagent_definitions: "agent.contextCategorySubagents",
  conversation: "agent.contextCategoryConversation",
  memory: "agent.contextCategoryMemory",
  attachments: "agent.contextCategoryAttachments",
  protocol_overhead: "agent.contextCategoryOverhead",
  other: "agent.contextCategoryOther",
};

function formatTokens(value: number): string {
  return tokenFormatter.format(Math.max(0, value));
}

export function AgentStatusPanel({
  sessionId,
  refreshKey,
  liveContext,
  onClose,
}: AgentStatusPanelProps) {
  const { t } = useTranslation();
  const [usage, setUsage] = useState<AgentSessionUsage | null>(null);
  const [loading, setLoading] = useState(false);
  const [unavailable, setUnavailable] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setUsage(null);
    setError(null);
    setUnavailable(!sessionId);
    if (!sessionId) return;

    setLoading(true);
    setUnavailable(false);
    void fetchAgentSessionUsage(sessionId)
      .then((payload) => {
        if (cancelled) return;
        setUsage(payload);
        setUnavailable(!payload.context?.latest);
      })
      .catch((reason: unknown) => {
        if (cancelled) return;
        if (reason instanceof ApiError && reason.status === 404) {
          setUnavailable(true);
          return;
        }
        setError(
          reason instanceof Error
            ? reason.message
            : t("agent.statusLoadFailed"),
        );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [refreshKey, sessionId, t]);

  const context = liveContext ?? usage?.context?.latest ?? null;
  const maxTokens = context?.context_window_tokens ?? 0;
  const usedTokens = context?.used_tokens ?? 0;
  const utilization = Math.max(
    0,
    Math.min(context?.utilization_ratio ?? 0, 1),
  );
  const nearingLimit = utilization >= 0.8;
  const totals = usage?.consumption?.totals;

  return (
    <section
      className={`dojo-agent-status${nearingLimit ? " dojo-agent-status--warning" : ""}`}
      aria-label={t("agent.statusTitle")}
      aria-live="polite"
    >
      <div className="dojo-agent-status__head">
        <strong>{t("agent.statusTitle")}</strong>
        <button
          type="button"
          onClick={onClose}
          aria-label={t("agent.statusClose")}
        >
          {t("agent.statusClose")}
        </button>
      </div>
      {loading ? (
        <p className="dojo-agent-status__notice">
          {t("agent.statusLoading")}
        </p>
      ) : null}
      {!loading && unavailable && !liveContext ? (
        <p className="dojo-agent-status__notice">
          {t("agent.statusUnavailable")}
        </p>
      ) : null}
      {!loading && error ? (
        <p className="dojo-agent-status__error">{error}</p>
      ) : null}
      {!loading && context ? (
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
          <div
            className="dojo-agent-status__meter dojo-agent-status__meter--segments"
            aria-label={t("agent.statusUtilization")}
          >
            {context.breakdown.map((item) => (
              <span
                key={`${item.category}:${item.source ?? ""}`}
                title={`${t(categoryLabelKeys[item.category])}: ${formatTokens(item.tokens)}`}
                style={{
                  backgroundColor: categoryColors[item.category],
                  width:
                    maxTokens > 0
                      ? `${Math.max(0, (item.tokens / maxTokens) * 100)}%`
                      : "0%",
                }}
              />
            ))}
          </div>
          <div className="dojo-agent-status__meter-meta">
            <span>
              {context.used_tokens_source === "provider_actual"
                ? t("agent.statusProviderActual")
                : t("agent.statusEstimated")}
            </span>
            <span>
              {t("agent.statusAvailable", {
                count: formatTokens(context.available_tokens),
              })}
            </span>
          </div>
          <ul className="dojo-agent-status__breakdown">
            {context.breakdown.map((item) => (
              <li key={`${item.category}:${item.source ?? ""}`}>
                <i
                  aria-hidden="true"
                  style={{ backgroundColor: categoryColors[item.category] }}
                />
                <span>{t(categoryLabelKeys[item.category])}</span>
                <strong>{formatTokens(item.tokens)}</strong>
              </li>
            ))}
          </ul>
          {totals ? (
            <dl className="dojo-agent-status__details">
              <div>
                <dt>{t("agent.statusInput")}</dt>
                <dd>{formatTokens(totals.input_tokens)}</dd>
              </div>
              <div>
                <dt>{t("agent.statusOutput")}</dt>
                <dd>{formatTokens(totals.output_tokens)}</dd>
              </div>
              <div>
                <dt>{t("agent.statusCumulative")}</dt>
                <dd>{formatTokens(totals.total_tokens)}</dd>
              </div>
              <div>
                <dt>{t("agent.statusCalls")}</dt>
                <dd>{totals.calls}</dd>
              </div>
            </dl>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
