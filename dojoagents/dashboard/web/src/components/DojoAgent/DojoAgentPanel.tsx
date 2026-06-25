import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import { useAgentModel } from "../../agent/AgentModelContext";
import { useAgentRun } from "../../agent/AgentRunContext";
import {
  AGENT_DRAFT_STORAGE_KEY,
  AGENT_SESSIONS_STORAGE_KEY,
  clearStreamDraft,
  loadStreamDraft,
  saveStreamDraft,
} from "../../agent/agentStorage";
import { useAgentSessions } from "../../agent/useAgentSessions";
import { useAgentPanelWidth } from "../../hooks/useAgentPanelWidth";
import { useTranslation } from "../../hooks/useTranslation";
import type { AppTab } from "../../navigation/appTab";
import type { AgentChatMessage } from "../../types/agent";
import { AgentModelSwitcher } from "../AgentModelSwitcher";
import "../AgentModelSwitcher.css";
import { AgentActivityTimeline } from "./AgentActivityTimeline";
import { AgentMarkdown } from "./AgentMarkdown";
import { AgentSuggestedQuestions } from "./AgentSuggestedQuestions";
import { AgentVizPanel } from "./viz/AgentVizPanel";
import {
  resolveActivitySteps,
  toggleThinkStep,
} from "../../utils/agentActivityTimeline";
import {
  collectVizBlocksFromSteps,
  stripRenderedChartBlocks,
} from "../../utils/agentVizContent";
import {
  finalizeIncompleteAssistantMessages,
  messagesForSessionPersist,
  prepareMessagesForApi,
} from "../../utils/agentMessages";
import "./DojoAgentPanel.css";
import { DojoButton } from "../ui";

interface DojoAgentPanelProps {
  open: boolean;
  pinned?: boolean;
  interactive?: boolean;
  sourceTab: AppTab;
  onClose: () => void;
}

function formatSessionTime(timestamp: number): string {
  const date = new Date(timestamp);
  const now = new Date();
  const sameDay =
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate();
  if (sameDay) {
    return date.toLocaleTimeString(undefined, {
      hour: "2-digit",
      minute: "2-digit",
    });
  }
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function HistoryIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden>
      <path
        d="M8 1.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.25"
      />
      <path
        d="M8 4.5v3.25l2.25 1.35"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.25"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function NewChatIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden>
      <path
        d="M3 4.5a1.5 1.5 0 0 1 1.5-1.5h7A1.5 1.5 0 0 1 13 4.5v5a1.5 1.5 0 0 1-1.5 1.5H7l-3 2.25V4.5Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.25"
        strokeLinejoin="round"
      />
      <path
        d="M8.25 6v3M6.75 7.5h3"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.25"
        strokeLinecap="round"
      />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden>
      <path
        d="M4.5 4.5l7 7M11.5 4.5l-7 7"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.25"
        strokeLinecap="round"
      />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden>
      <path
        d="M2.5 4.5h9M5.25 4.5V3.25a.75.75 0 0 1 .75-.75h2a.75.75 0 0 1 .75.75V4.5M5.5 6.75v3.5M8.5 6.75v3.5M4 4.5l.35 6.3a1 1 0 0 0 1 .85h3.3a1 1 0 0 0 1-.85L10 4.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.1"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function DojoAgentPanel({
  open,
  pinned = false,
  interactive = false,
  sourceTab,
  onClose,
}: DojoAgentPanelProps) {
  const { t, locale } = useTranslation();
  const { width: panelWidth, resizing, onResizeStart } = useAgentPanelWidth();
  const { selectedModelId, agentReady, selectedModel, setSelectedModelId } =
    useAgentModel();
  const {
    sessions,
    activeSessionId,
    activeSession,
    createSession,
    selectSession,
    ensureActiveSession,
    replaceSessionMessages,
    deleteSession,
    reloadFromStorage,
  } = useAgentSessions();
  const {
    getSessionRun,
    startRun,
    stopRun,
    isSessionRunning,
    wireRunCallbacks,
    toggleRunThinkBlock,
  } = useAgentRun();

  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [switchingSessionId, setSwitchingSessionId] = useState<string | null>(
    null,
  );
  const [recoveredNotice, setRecoveredNotice] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const persistTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const sessionRun = getSessionRun(activeSessionId);
  const streaming = isSessionRunning(activeSessionId);
  const messages = streaming
    ? sessionRun.draftMessages
    : (activeSession?.messages ?? []);
  const livePhase = sessionRun.livePhase;
  const retryNotice = sessionRun.retryNotice;
  const panelError = error ?? sessionRun.error;

  useEffect(() => {
    const draft = loadStreamDraft();
    if (!draft?.interrupted) return;
    const finalized = finalizeIncompleteAssistantMessages(
      draft.messages,
      t("agent.interrupted"),
    );
    replaceSessionMessages(draft.sessionId, finalized, draft.modelId);
    selectSession(draft.sessionId);
    setRecoveredNotice(true);
    clearStreamDraft();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- recover once on mount
  }, []);

  useEffect(() => {
    if (!recoveredNotice) return;
    const timer = window.setTimeout(() => setRecoveredNotice(false), 12000);
    return () => window.clearTimeout(timer);
  }, [recoveredNotice]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streaming, sessionRun.draftMessages]);

  const flushPersistDraft = useCallback(
    (
      sessionId: string,
      nextMessages: AgentChatMessage[],
      interrupted = false,
    ) => {
      const toSave = interrupted
        ? finalizeIncompleteAssistantMessages(
            nextMessages,
            t("agent.interrupted"),
          )
        : messagesForSessionPersist(nextMessages);
      replaceSessionMessages(sessionId, toSave, selectedModelId);
      saveStreamDraft({
        sessionId,
        modelId: selectedModelId,
        messages: interrupted ? toSave : nextMessages,
        updatedAt: Date.now(),
        interrupted,
      });
    },
    [replaceSessionMessages, selectedModelId, t],
  );

  const schedulePersistDraft = useCallback(
    (sessionId: string, nextMessages: AgentChatMessage[]) => {
      if (persistTimerRef.current) {
        window.clearTimeout(persistTimerRef.current);
      }
      persistTimerRef.current = window.setTimeout(() => {
        flushPersistDraft(sessionId, nextMessages, false);
        persistTimerRef.current = null;
      }, 350);
    },
    [flushPersistDraft],
  );

  const persistMessages = useCallback(
    (sessionId: string, nextMessages: AgentChatMessage[]) => {
      if (persistTimerRef.current) {
        window.clearTimeout(persistTimerRef.current);
        persistTimerRef.current = null;
      }
      replaceSessionMessages(sessionId, nextMessages, selectedModelId);
      clearStreamDraft();
    },
    [replaceSessionMessages, selectedModelId],
  );

  useEffect(() => {
    if (!open) return;
    reloadFromStorage();
  }, [open, reloadFromStorage]);

  useEffect(() => {
    if (!activeSessionId || !isSessionRunning(activeSessionId)) return;
    wireRunCallbacks(activeSessionId, {
      onComplete: (finalMessages) => {
        persistMessages(activeSessionId, finalMessages);
      },
      onPersistDraft: (draft) => {
        schedulePersistDraft(activeSessionId, draft);
      },
    });
  }, [
    activeSessionId,
    isSessionRunning,
    persistMessages,
    schedulePersistDraft,
    wireRunCallbacks,
  ]);

  const handleNewSession = useCallback(() => {
    setError(null);
    setInput("");
    setHistoryOpen(false);
    setRecoveredNotice(false);
    clearStreamDraft();
    createSession(selectedModelId);
  }, [createSession, selectedModelId]);

  const handleSelectSession = useCallback(
    (sessionId: string) => {
      if (sessionId === activeSessionId) {
        setHistoryOpen(false);
        return;
      }
      setSwitchingSessionId(sessionId);
      setError(null);
      setInput("");
      const session = sessions.find((item) => item.id === sessionId);
      if (session) {
        setSelectedModelId(session.modelId);
      }
      selectSession(sessionId);
      window.setTimeout(() => {
        setSwitchingSessionId(null);
        setHistoryOpen(false);
      }, 120);
    },
    [activeSessionId, selectSession, sessions, setSelectedModelId],
  );

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || streaming || !selectedModel?.available) return;

    const sessionId = ensureActiveSession(selectedModelId);
    const userMessage: AgentChatMessage = { role: "user", content: text };
    const pendingAssistant: AgentChatMessage = {
      role: "assistant",
      content: "",
      activitySteps: [],
    };
    const nextMessages = [...messages, userMessage, pendingAssistant];
    const uiLocale = locale === "zh" ? "zh" : "en";

    setInput("");
    setError(null);

    try {
      await startRun({
        sessionId,
        modelId: selectedModelId,
        locale,
        draftMessages: nextMessages,
        apiMessages: prepareMessagesForApi(
          [...messages, userMessage],
          t("agent.toolsComplete"),
        ),
        toolsCompleteLabel: t("agent.toolsComplete"),
        responseCompleteLabel: t("agent.responseComplete"),
        stoppedLabel: t("agent.stopped"),
        uiLocale,
        formatRetryNotice: (attempt, max) =>
          t("agent.retrying", { attempt, max }),
        onComplete: (finalMessages) => {
          persistMessages(sessionId, finalMessages);
          textareaRef.current?.focus();
        },
        onPersistDraft: (draft) => {
          schedulePersistDraft(sessionId, draft);
        },
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("agent.sendFailed"));
      setInput(text);
    }
  }, [
    ensureActiveSession,
    locale,
    messages,
    persistMessages,
    schedulePersistDraft,
    selectedModel?.available,
    input,
    startRun,
    streaming,
    selectedModelId,
    t,
  ]);

  const handleStop = useCallback(() => {
    if (!streaming || !activeSessionId) return;
    void stopRun(activeSessionId);
    textareaRef.current?.focus();
  }, [activeSessionId, stopRun, streaming]);

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void handleSend();
    }
  };

  const canSend =
    Boolean(selectedModel?.available) && input.trim().length > 0 && !streaming;
  const displayMessages = messages;

  const toggleThinkBlock = useCallback(
    (messageIndex: number, blockId: string) => {
      if (!activeSessionId) return;
      const isStreamingAssistant =
        streaming &&
        displayMessages[messageIndex]?.role === "assistant" &&
        messageIndex === displayMessages.length - 1;
      if (isStreamingAssistant) {
        toggleRunThinkBlock(activeSessionId, blockId);
        return;
      }
      const next = displayMessages.map((message, index) => {
        if (index !== messageIndex) return message;
        const steps = resolveActivitySteps(message);
        if (
          !steps.some(
            (step) => step.kind === "think" && step.block.id === blockId,
          )
        ) {
          return message;
        }
        return {
          ...message,
          activitySteps: toggleThinkStep(steps, blockId),
        };
      });
      replaceSessionMessages(activeSessionId, next, selectedModelId);
    },
    [
      activeSessionId,
      displayMessages,
      replaceSessionMessages,
      selectedModelId,
      streaming,
      toggleRunThinkBlock,
    ],
  );

  const isOpen = pinned || open;

  return (
    <aside
      id="dojo-agent-panel"
      className={`dojo-agent-panel ${isOpen ? "dojo-agent-panel--open" : ""}${
        pinned ? " dojo-agent-panel--pinned" : ""
      }${interactive ? " dojo-agent-panel--interactive" : ""}${
        resizing ? " dojo-agent-panel--resizing" : ""
      }`}
      style={isOpen ? { width: panelWidth } : undefined}
      role="complementary"
      aria-labelledby="dojo-agent-title"
      aria-hidden={!isOpen}
    >
      {isOpen ? (
        <div
          className="dojo-agent-panel__resize-handle"
          role="separator"
          aria-orientation="vertical"
          aria-label={t("agent.resizePanel")}
          title={t("agent.resizePanel")}
          onPointerDown={onResizeStart}
        />
      ) : null}
      <div className="dojo-agent-panel__inner">
        <header className="dojo-agent-panel__head">
          <h2 id="dojo-agent-title" className="dojo-agent-panel__title">
            DojoAgent
          </h2>
          <div className="dojo-agent-panel__head-actions">
            <button
              type="button"
              className={`dojo-agent-panel__toolbar-btn ${
                historyOpen ? "dojo-agent-panel__toolbar-btn--active" : ""
              }`}
              aria-expanded={historyOpen}
              aria-label={t("agent.history")}
              title={t("agent.history")}
              onClick={() => setHistoryOpen((prev) => !prev)}
            >
              <HistoryIcon />
            </button>
            <button
              type="button"
              className="dojo-agent-panel__toolbar-btn"
              aria-label={t("agent.newChat")}
              title={t("agent.newChat")}
              onClick={handleNewSession}
            >
              <NewChatIcon />
            </button>
            {!pinned ? (
              <button
                type="button"
                className="dojo-agent-panel__toolbar-btn dojo-agent-panel__toolbar-btn--close"
                aria-label={t("agent.close")}
                title={t("agent.close")}
                onClick={onClose}
              >
                <CloseIcon />
              </button>
            ) : null}
          </div>
        </header>

        {historyOpen && (
          <div
            className="dojo-agent-panel__history"
            role="navigation"
            aria-label={t("agent.history")}
          >
            <div className="dojo-agent-panel__history-head">
              <span className="dojo-agent-panel__history-label">
                {t("agent.history")}
              </span>
              {sessions.length > 0 ? (
                <span className="dojo-agent-panel__history-count">
                  {sessions.length}
                </span>
              ) : null}
            </div>
            {sessions.length === 0 ? (
              <div className="dojo-agent-panel__history-empty">
                <HistoryIcon />
                <p>{t("agent.noHistory")}</p>
              </div>
            ) : (
              <ul className="dojo-agent-panel__history-list">
                {sessions.map((session) => {
                  const isActive = session.id === activeSessionId;
                  const isLoading = session.id === switchingSessionId;
                  const messageCount = session.messages.length;
                  return (
                    <li key={session.id}>
                      <div
                        className={`dojo-agent-panel__history-item ${
                          isActive
                            ? "dojo-agent-panel__history-item--active"
                            : ""
                        }${isLoading ? " dojo-agent-panel__history-item--loading" : ""}`}
                      >
                        <button
                          type="button"
                          className="dojo-agent-panel__history-select"
                          disabled={isLoading}
                          onClick={() => handleSelectSession(session.id)}
                        >
                          <span className="dojo-agent-panel__history-title">
                            {session.title || t("agent.newChatTitle")}
                          </span>
                          <span className="dojo-agent-panel__history-meta">
                            {messageCount > 0
                              ? t("agent.messageCount", { count: messageCount })
                              : t("agent.newChatTitle")}
                            <span className="dojo-agent-panel__history-meta-sep">
                              ·
                            </span>
                            {formatSessionTime(session.updatedAt)}
                          </span>
                        </button>
                        <button
                          type="button"
                          className="dojo-agent-panel__history-delete"
                          aria-label={t("agent.deleteSession")}
                          disabled={isLoading}
                          onClick={() => deleteSession(session.id)}
                        >
                          <TrashIcon />
                        </button>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
            <p
              className="dojo-agent-panel__storage"
              title={t("agent.storageDetail", {
                sessionsKey: AGENT_SESSIONS_STORAGE_KEY,
                draftKey: AGENT_DRAFT_STORAGE_KEY,
              })}
            >
              <span className="dojo-agent-panel__storage-label">
                {t("agent.storageLabel")}
              </span>
              <code className="dojo-agent-panel__storage-key">
                {AGENT_SESSIONS_STORAGE_KEY}
              </code>
            </p>
          </div>
        )}

        <div className="dojo-agent-panel__body">
          {switchingSessionId ? (
            <div className="dojo-agent-panel__loading" aria-live="polite">
              <div className="dojo-agent-panel__loading-spinner" />
              <p>{t("agent.loadingSession")}</p>
            </div>
          ) : null}
          <div
            className={`dojo-agent-panel__messages${
              switchingSessionId ? " dojo-agent-panel__messages--hidden" : ""
            }`}
            role="log"
            aria-live="polite"
          >
            {displayMessages.length === 0 && !switchingSessionId ? (
              <div className="dojo-agent-panel__empty-state">
                <AgentSuggestedQuestions
                  sourceTab={sourceTab}
                  onSelect={(question) => {
                    setInput(question);
                    textareaRef.current?.focus();
                  }}
                />
              </div>
            ) : null}
            {recoveredNotice ? (
              <p className="dojo-agent-panel__recovered" role="status">
                {t("agent.recoveredNotice")}
              </p>
            ) : null}
            {displayMessages.map((message, index) => {
              const isStreamingAssistant =
                streaming &&
                message.role === "assistant" &&
                index === displayMessages.length - 1;
              const activitySteps = resolveActivitySteps(message);
              const hasActivity = activitySteps.length > 0;
              const messageVizBlocks =
                message.role === "assistant"
                  ? collectVizBlocksFromSteps(activitySteps)
                  : [];
              const displayContent =
                message.role === "assistant"
                  ? stripRenderedChartBlocks(
                      message.content,
                      messageVizBlocks.length > 0,
                    )
                  : message.content;
              const showAssistantBubble =
                message.role === "assistant" &&
                (displayContent ||
                  hasActivity ||
                  (isStreamingAssistant && livePhase));

              if (message.role === "assistant" && !showAssistantBubble) {
                return null;
              }

              return (
                <div
                  key={`${message.role}-${index}`}
                  className={`dojo-agent-panel__message dojo-agent-panel__message--${message.role}`}
                >
                  <div
                    className={`dojo-agent-panel__bubble ${
                      isStreamingAssistant
                        ? "dojo-agent-panel__bubble--streaming"
                        : ""
                    }`}
                  >
                    {message.role === "user" ? (
                      <p className="dojo-agent-panel__user-text">
                        {message.content}
                      </p>
                    ) : (
                      <>
                        <AgentActivityTimeline
                          steps={activitySteps}
                          phase={isStreamingAssistant ? livePhase : null}
                          streaming={isStreamingAssistant}
                          retryNotice={
                            isStreamingAssistant ? retryNotice : null
                          }
                          onToggleThinkBlock={(blockId) =>
                            toggleThinkBlock(index, blockId)
                          }
                        />
                        {messageVizBlocks.length > 0 ? (
                          <AgentVizPanel blocks={messageVizBlocks} />
                        ) : null}
                        {displayContent ? (
                          <AgentMarkdown
                            content={displayContent}
                            streaming={
                              isStreamingAssistant && !!displayContent
                            }
                          />
                        ) : null}
                        {isStreamingAssistant &&
                        !displayContent &&
                        !livePhase &&
                        !hasActivity ? (
                          <p className="dojo-agent-panel__waiting">
                            {t("agent.waiting")}
                          </p>
                        ) : null}
                      </>
                    )}
                  </div>
                </div>
              );
            })}
            <div ref={messagesEndRef} />
          </div>
        </div>

        <footer className="dojo-agent-panel__composer">
          {!agentReady && (
            <p className="dojo-agent-panel__hint">
              {t("agent.apiNotConfigured")}
            </p>
          )}
          {panelError && (
            <p className="dojo-agent-panel__error">{panelError}</p>
          )}
          <textarea
            ref={textareaRef}
            className="dojo-agent-panel__input"
            rows={3}
            value={input}
            placeholder={t("agent.placeholder")}
            disabled={!selectedModel?.available || streaming}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={handleKeyDown}
          />
          <div className="dojo-agent-panel__composer-bar">
            <AgentModelSwitcher variant="composer" />
            {streaming ? (
              <DojoButton
                variant="secondary"
                size="sm"
                aria-label={t("agent.stop")}
                onClick={handleStop}
              >
                {t("agent.stop")}
              </DojoButton>
            ) : (
              <DojoButton
                variant="secondary"
                size="sm"
                disabled={!canSend}
                aria-label={t("agent.send")}
                onClick={() => void handleSend()}
              >
                {t("agent.send")}
              </DojoButton>
            )}
          </div>
        </footer>
      </div>
    </aside>
  );
}
