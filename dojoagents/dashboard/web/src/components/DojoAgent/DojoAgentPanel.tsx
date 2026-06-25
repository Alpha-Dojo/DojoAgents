import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { useAgentModel } from '../../agent/AgentModelContext';
import {
  AGENT_DRAFT_STORAGE_KEY,
  AGENT_SESSIONS_STORAGE_KEY,
  clearStreamDraft,
  loadStreamDraft,
  saveStreamDraft,
} from '../../agent/agentStorage';
import { useAgentSessions } from '../../agent/useAgentSessions';
import { streamAgentChat } from '../../api/agent';
import { useAgentPanelWidth } from '../../hooks/useAgentPanelWidth';
import { useTranslation } from '../../hooks/useTranslation';
import type { AppTab } from '../../navigation/appTab';
import type {
  AgentChatMessage,
  AgentEvalHintItem,
  AgentThinkBlock,
  AgentToolActivityItem,
} from '../../types/agent';
import { AgentModelSwitcher } from '../AgentModelSwitcher';
import '../AgentModelSwitcher.css';
import { AgentEvalHints } from './AgentEvalHints';
import { AgentMarkdown } from './AgentMarkdown';
import { AgentSuggestedQuestions } from './AgentSuggestedQuestions';
import { AgentThinking } from './AgentThinking';
import { AgentToolActivity } from './AgentToolActivity';
import type { AgentVizBlock } from '../../types/agentViz';
import { syncFolioAfterAgentSession, syncFolioFromAgentTool } from '../../utils/agentFolioSync';
import {
  finalizeIncompleteAssistantMessages,
  messagesForSessionPersist,
  prepareMessagesForApi,
} from '../../utils/agentMessages';
import { formatToolResultData } from '../../utils/agentToolDetail';
import './DojoAgentPanel.css';

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
    return date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
  }
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
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

function updateAssistantMessage(
  messages: AgentChatMessage[],
  patch: Partial<AgentChatMessage>,
): AgentChatMessage[] {
  if (messages.length === 0) return messages;
  const updated = [...messages];
  const last = updated[updated.length - 1];
  if (last.role !== 'assistant') return messages;
  updated[updated.length - 1] = { ...last, ...patch };
  return updated;
}

function appendToolStart(
  activity: AgentToolActivityItem[] | undefined,
  tool: string,
  args: Record<string, unknown>,
): AgentToolActivityItem[] {
  return [...(activity ?? []), { tool, status: 'running', arguments: args }];
}

function resolveToolResult(
  activity: AgentToolActivityItem[] | undefined,
  tool: string,
  ok: boolean,
  latencyMs: number,
  locale: 'zh' | 'en',
  error?: string | null,
  data?: {
    portfolio_id?: string;
    name?: string;
    holdings_count?: number;
    holdings_by_market?: Record<string, number>;
    tickers?: string[];
  } | null,
  vizBlocks?: AgentVizBlock[],
): AgentToolActivityItem[] {
  const items = [...(activity ?? [])];
  const runningIndex = items.findIndex((item) => item.tool === tool && item.status === 'running');
  const resultSummary = ok ? formatToolResultData(data, locale) : null;
  const next: AgentToolActivityItem = {
    tool,
    status: ok ? 'done' : 'error',
    latencyMs,
    error: ok ? null : error ?? null,
    resultSummary,
    vizBlocks: ok && vizBlocks?.length ? vizBlocks : undefined,
    arguments: runningIndex >= 0 ? items[runningIndex].arguments : undefined,
  };
  if (runningIndex >= 0) {
    items[runningIndex] = { ...items[runningIndex], ...next };
    return items;
  }
  return [...items, next];
}

function appendEvalHint(
  hints: AgentEvalHintItem[] | undefined,
  issues: string[],
): AgentEvalHintItem[] {
  if (issues.length === 0) return hints ?? [];
  const key = issues.join('\u0001');
  const existing = hints ?? [];
  if (existing.some((hint) => hint.issues.join('\u0001') === key)) {
    return existing;
  }
  return [...existing, { id: crypto.randomUUID(), issues: [...issues] }];
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
  const { selectedModelId, geminiConfigured, setSelectedModelId } = useAgentModel();
  const {
    sessions,
    activeSessionId,
    activeSession,
    createSession,
    selectSession,
    ensureActiveSession,
    replaceSessionMessages,
    deleteSession,
  } = useAgentSessions();

  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [switchingSessionId, setSwitchingSessionId] = useState<string | null>(null);
  const [draftMessages, setDraftMessages] = useState<AgentChatMessage[]>([]);
  const [livePhase, setLivePhase] = useState<
    'planning' | 'tools' | 'answering' | 'done' | null
  >(null);
  const [retryNotice, setRetryNotice] = useState<string | null>(null);
  const [recoveredNotice, setRecoveredNotice] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const persistTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const streamingSessionIdRef = useRef<string | null>(null);
  const draftMessagesRef = useRef<AgentChatMessage[]>([]);

  const messages = activeSession?.messages ?? draftMessages;

  useEffect(() => {
    draftMessagesRef.current = draftMessages;
  }, [draftMessages]);

  useEffect(() => {
    const draft = loadStreamDraft();
    if (!draft?.interrupted) return;
    const finalized = finalizeIncompleteAssistantMessages(
      draft.messages,
      t('agent.interrupted'),
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
    const flushOnUnload = () => {
      const sessionId = streamingSessionIdRef.current;
      const msgs = draftMessagesRef.current;
      if (!sessionId || msgs.length === 0) return;
      replaceSessionMessages(sessionId, msgs, selectedModelId);
      saveStreamDraft({
        sessionId,
        modelId: selectedModelId,
        messages: msgs,
        updatedAt: Date.now(),
        interrupted: true,
      });
    };
    window.addEventListener('beforeunload', flushOnUnload);
    return () => window.removeEventListener('beforeunload', flushOnUnload);
  }, [replaceSessionMessages, selectedModelId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streaming, draftMessages]);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  const flushPersistDraft = useCallback(
    (sessionId: string, nextMessages: AgentChatMessage[], interrupted = false) => {
      const toSave = interrupted
        ? finalizeIncompleteAssistantMessages(nextMessages, t('agent.interrupted'))
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
      streamingSessionIdRef.current = null;
      replaceSessionMessages(sessionId, nextMessages, selectedModelId);
      clearStreamDraft();
      setDraftMessages([]);
    },
    [replaceSessionMessages, selectedModelId],
  );

  const handleNewSession = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setStreaming(false);
    setError(null);
    setInput('');
    setHistoryOpen(false);
    setLivePhase(null);
    setRetryNotice(null);
    setRecoveredNotice(false);
    setDraftMessages([]);
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
      abortRef.current?.abort();
      abortRef.current = null;
      setStreaming(false);
      setError(null);
      setInput('');
      setDraftMessages([]);
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
    if (!text || streaming || !geminiConfigured) return;

    const sessionId = ensureActiveSession(selectedModelId);
    const userMessage: AgentChatMessage = { role: 'user', content: text };
    const pendingAssistant: AgentChatMessage = {
      role: 'assistant',
      content: '',
      toolActivity: [],
      thinkBlocks: [],
      evalHints: [],
    };
    const nextMessages = [...messages, userMessage, pendingAssistant];

    setDraftMessages(nextMessages);
    streamingSessionIdRef.current = sessionId;
    flushPersistDraft(sessionId, nextMessages, false);
    setInput('');
    setStreaming(true);
    setError(null);

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    let assistantText = '';
    let assistantTools: AgentToolActivityItem[] = [];
    let assistantThinkBlocks: AgentThinkBlock[] = [];
    let assistantEvalHints: AgentEvalHintItem[] = [];
    let currentThinkId: string | null = null;
    const uiLocale = locale === 'zh' ? 'zh' : 'en';
    setLivePhase('planning');
    setRetryNotice(null);

    const patchAssistant = (patch: Partial<AgentChatMessage>) => {
      setDraftMessages((prev) => {
        const updated = updateAssistantMessage(prev, {
          content: assistantText,
          toolActivity: assistantTools,
          thinkBlocks: assistantThinkBlocks,
          evalHints: assistantEvalHints,
          ...patch,
        });
        schedulePersistDraft(sessionId, updated);
        return updated;
      });
    };

    await streamAgentChat(
      {
        model_id: selectedModelId,
        locale,
        messages: prepareMessagesForApi(
          [...messages, userMessage],
          t('agent.toolsComplete'),
        ),
      },
      {
        onPhase: (phase) => {
          setLivePhase(phase);
        },
        onRetry: ({ attempt, max_attempts }) => {
          setRetryNotice(t('agent.retrying', { attempt, max: max_attempts }));
          setLivePhase('planning');
        },
        onThinkStart: () => {
          if (currentThinkId) {
            assistantThinkBlocks = assistantThinkBlocks.map((block) =>
              block.id === currentThinkId
                ? { ...block, done: true, collapsed: true }
                : block,
            );
          }
          currentThinkId = crypto.randomUUID();
          assistantThinkBlocks = [
            ...assistantThinkBlocks,
            { id: currentThinkId, text: '', collapsed: false, done: false },
          ];
          patchAssistant({});
        },
        onThinkDelta: (text) => {
          if (!currentThinkId) return;
          assistantThinkBlocks = assistantThinkBlocks.map((block) =>
            block.id === currentThinkId ? { ...block, text: block.text + text } : block,
          );
          patchAssistant({});
        },
        onThinkEnd: () => {
          if (!currentThinkId) return;
          assistantThinkBlocks = assistantThinkBlocks.map((block) =>
            block.id === currentThinkId
              ? { ...block, done: true, collapsed: true }
              : block,
          );
          currentThinkId = null;
          patchAssistant({});
        },
        onDelta: (delta) => {
          assistantText += delta;
          patchAssistant({});
        },
        onToolStart: (tool, args) => {
          assistantTools = appendToolStart(assistantTools, tool, args);
          patchAssistant({});
        },
        onToolResult: ({ tool, ok, latency_ms, error: toolError, data, viz_blocks }) => {
          assistantTools = resolveToolResult(
            assistantTools,
            tool,
            ok,
            latency_ms,
            uiLocale,
            toolError,
            data,
            viz_blocks,
          );
          patchAssistant({});
          // @ts-ignore - data parameter type from streaming is unknown
          void syncFolioFromAgentTool(tool, ok, data);
        },
        onEvalHint: ({ issues }) => {
          assistantEvalHints = appendEvalHint(assistantEvalHints, issues);
          patchAssistant({});
        },
        onDone: () => {
          syncFolioAfterAgentSession(
            assistantTools.map((item) => ({
              tool: item.tool,
              ok: item.status === 'done',
            })),
          );
          setLivePhase('done');
          setRetryNotice(null);
          assistantThinkBlocks = assistantThinkBlocks.map((block) => ({
            ...block,
            done: true,
            collapsed: true,
          }));
          const fallbackContent =
            assistantText ||
            (assistantTools.length > 0 ? t('agent.toolsComplete') : t('agent.responseComplete'));
          const finalMessages = [
            ...messages,
            userMessage,
            {
              role: 'assistant' as const,
              content: fallbackContent,
              toolActivity: assistantTools.length > 0 ? assistantTools : undefined,
              thinkBlocks: assistantThinkBlocks.length > 0 ? assistantThinkBlocks : undefined,
              evalHints: assistantEvalHints.length > 0 ? assistantEvalHints : undefined,
            },
          ];
          persistMessages(sessionId, finalMessages);
          setStreaming(false);
          abortRef.current = null;
          window.setTimeout(() => setLivePhase(null), 1200);
          textareaRef.current?.focus();
        },
        onError: (message) => {
          syncFolioAfterAgentSession(
            assistantTools.map((item) => ({
              tool: item.tool,
              ok: item.status === 'done',
            })),
          );
          setError(message);
          setLivePhase(null);
          setRetryNotice(null);
          if (assistantText || assistantTools.length > 0 || assistantThinkBlocks.length > 0) {
            const partialMessages = [
              ...messages,
              userMessage,
              {
                role: 'assistant' as const,
                content: assistantText || message,
                toolActivity: assistantTools.length > 0 ? assistantTools : undefined,
                thinkBlocks: assistantThinkBlocks.length > 0 ? assistantThinkBlocks : undefined,
                evalHints: assistantEvalHints.length > 0 ? assistantEvalHints : undefined,
              },
            ];
            persistMessages(sessionId, partialMessages);
          } else {
            setInput(text);
          }
          setDraftMessages([]);
          setStreaming(false);
          abortRef.current = null;
          textareaRef.current?.focus();
        },
      },
      controller.signal,
    );
  }, [
    ensureActiveSession,
    flushPersistDraft,
    geminiConfigured,
    input,
    locale,
    messages,
    persistMessages,
    schedulePersistDraft,
    selectedModelId,
    streaming,
    t,
  ]);

  const handleStop = useCallback(() => {
    if (!streaming) return;
    abortRef.current?.abort();
    abortRef.current = null;
    const sessionId = ensureActiveSession(selectedModelId);
    setDraftMessages((prev) => {
      if (prev.length === 0) return prev;
      const finalized = prev.map((message, index) =>
        index === prev.length - 1 && message.role === 'assistant'
          ? { ...message, content: message.content || t('agent.stopped') }
          : message,
      );
      persistMessages(sessionId, finalized);
      return [];
    });
    setStreaming(false);
    setLivePhase(null);
    setRetryNotice(null);
    textareaRef.current?.focus();
  }, [ensureActiveSession, persistMessages, selectedModelId, streaming, t]);

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      void handleSend();
    }
  };

  const canSend = geminiConfigured && input.trim().length > 0 && !streaming;
  const displayMessages = draftMessages.length > 0 ? draftMessages : messages;

  const toggleThinkBlock = useCallback(
    (messageIndex: number, blockId: string) => {
      const source = draftMessages.length > 0 ? draftMessages : messages;
      const next = source.map((message, index) => {
        if (index !== messageIndex || !message.thinkBlocks) return message;
        return {
          ...message,
          thinkBlocks: message.thinkBlocks.map((block) =>
            block.id === blockId ? { ...block, collapsed: !block.collapsed } : block,
          ),
        };
      });
      if (draftMessages.length > 0) {
        setDraftMessages(next);
      } else if (activeSessionId) {
        replaceSessionMessages(activeSessionId, next, selectedModelId);
      }
    },
    [activeSessionId, draftMessages, messages, replaceSessionMessages, selectedModelId],
  );

  const isOpen = pinned || open;

  return (
    <aside
      id="dojo-agent-panel"
      className={`dojo-agent-panel ${isOpen ? 'dojo-agent-panel--open' : ''}${
        pinned ? ' dojo-agent-panel--pinned' : ''
      }${interactive ? ' dojo-agent-panel--interactive' : ''}${
        resizing ? ' dojo-agent-panel--resizing' : ''
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
          aria-label={t('agent.resizePanel')}
          title={t('agent.resizePanel')}
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
              historyOpen ? 'dojo-agent-panel__toolbar-btn--active' : ''
            }`}
            aria-expanded={historyOpen}
            aria-label={t('agent.history')}
            title={t('agent.history')}
            onClick={() => setHistoryOpen((prev) => !prev)}
          >
            <HistoryIcon />
          </button>
          <button
            type="button"
            className="dojo-agent-panel__toolbar-btn"
            aria-label={t('agent.newChat')}
            title={t('agent.newChat')}
            onClick={handleNewSession}
          >
            <NewChatIcon />
          </button>
          {!pinned ? (
            <button
              type="button"
              className="dojo-agent-panel__toolbar-btn dojo-agent-panel__toolbar-btn--close"
              aria-label={t('agent.close')}
              title={t('agent.close')}
              onClick={onClose}
            >
              <CloseIcon />
            </button>
          ) : null}
        </div>
      </header>

      {historyOpen && (
        <div className="dojo-agent-panel__history" role="navigation" aria-label={t('agent.history')}>
          <div className="dojo-agent-panel__history-head">
            <span className="dojo-agent-panel__history-label">{t('agent.history')}</span>
            {sessions.length > 0 ? (
              <span className="dojo-agent-panel__history-count">{sessions.length}</span>
            ) : null}
          </div>
          {sessions.length === 0 ? (
            <div className="dojo-agent-panel__history-empty">
              <HistoryIcon />
              <p>{t('agent.noHistory')}</p>
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
                        isActive ? 'dojo-agent-panel__history-item--active' : ''
                      }${isLoading ? ' dojo-agent-panel__history-item--loading' : ''}`}
                    >
                      <button
                        type="button"
                        className="dojo-agent-panel__history-select"
                        disabled={isLoading}
                        onClick={() => handleSelectSession(session.id)}
                      >
                        <span className="dojo-agent-panel__history-title">
                          {session.title || t('agent.newChatTitle')}
                        </span>
                        <span className="dojo-agent-panel__history-meta">
                          {messageCount > 0
                            ? t('agent.messageCount', { count: messageCount })
                            : t('agent.newChatTitle')}
                          <span className="dojo-agent-panel__history-meta-sep">·</span>
                          {formatSessionTime(session.updatedAt)}
                        </span>
                      </button>
                      <button
                        type="button"
                        className="dojo-agent-panel__history-delete"
                        aria-label={t('agent.deleteSession')}
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
          <p className="dojo-agent-panel__storage" title={t('agent.storageDetail', {
            sessionsKey: AGENT_SESSIONS_STORAGE_KEY,
            draftKey: AGENT_DRAFT_STORAGE_KEY,
          })}>
            <span className="dojo-agent-panel__storage-label">{t('agent.storageLabel')}</span>
            <code className="dojo-agent-panel__storage-key">{AGENT_SESSIONS_STORAGE_KEY}</code>
          </p>
        </div>
      )}

      <div className="dojo-agent-panel__body">
        {switchingSessionId ? (
          <div className="dojo-agent-panel__loading" aria-live="polite">
            <div className="dojo-agent-panel__loading-spinner" />
            <p>{t('agent.loadingSession')}</p>
          </div>
        ) : null}
        <div
          className={`dojo-agent-panel__messages${
            switchingSessionId ? ' dojo-agent-panel__messages--hidden' : ''
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
              {t('agent.recoveredNotice')}
            </p>
          ) : null}
          {displayMessages.map((message, index) => {
            const isStreamingAssistant =
              streaming &&
              message.role === 'assistant' &&
              index === displayMessages.length - 1;
            const toolActivity = message.toolActivity ?? [];
            const thinkBlocks = message.thinkBlocks ?? [];
            const evalHints = message.evalHints ?? [];
            const hasToolActivity = toolActivity.length > 0;
            const hasThinkBlocks = thinkBlocks.length > 0;
            const hasEvalHints = evalHints.length > 0;
            const showAssistantBubble =
              message.role === 'assistant' &&
              (message.content ||
                hasToolActivity ||
                hasThinkBlocks ||
                hasEvalHints ||
                (isStreamingAssistant && livePhase));

            if (message.role === 'assistant' && !showAssistantBubble) {
              return null;
            }

            return (
              <div
                key={`${message.role}-${index}`}
                className={`dojo-agent-panel__message dojo-agent-panel__message--${message.role}`}
              >
                <div
                  className={`dojo-agent-panel__bubble ${
                    isStreamingAssistant ? 'dojo-agent-panel__bubble--streaming' : ''
                  }`}
                >
                  {message.role === 'user' ? (
                    <p className="dojo-agent-panel__user-text">{message.content}</p>
                  ) : (
                    <>
                      <AgentThinking
                        blocks={thinkBlocks}
                        phase={isStreamingAssistant ? livePhase : null}
                        streaming={isStreamingAssistant}
                        retryNotice={isStreamingAssistant ? retryNotice : null}
                        onToggleBlock={(blockId) => toggleThinkBlock(index, blockId)}
                      />
                      {evalHints.map((hint) => (
                        <AgentEvalHints key={hint.id} issues={hint.issues} />
                      ))}
                      <AgentToolActivity items={toolActivity} />
                      {message.content ? (
                        <AgentMarkdown
                          content={message.content}
                          streaming={isStreamingAssistant && !!message.content}
                        />
                      ) : null}
                      {isStreamingAssistant && !message.content && !livePhase && !hasToolActivity ? (
                        <p className="dojo-agent-panel__waiting">{t('agent.waiting')}</p>
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
        {!geminiConfigured && (
          <p className="dojo-agent-panel__hint">{t('agent.apiNotConfigured')}</p>
        )}
        {error && <p className="dojo-agent-panel__error">{error}</p>}
        <textarea
          ref={textareaRef}
          className="dojo-agent-panel__input"
          rows={3}
          value={input}
          placeholder={t('agent.placeholder')}
          disabled={!geminiConfigured || streaming}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={handleKeyDown}
        />
        <div className="dojo-agent-panel__composer-bar">
          <AgentModelSwitcher variant="composer" />
          {streaming ? (
            <button
              type="button"
              className="dojo-agent-panel__stop"
              aria-label={t('agent.stop')}
              onClick={handleStop}
            >
              {t('agent.stop')}
            </button>
          ) : (
            <button
              type="button"
              className="dojo-agent-panel__send"
              disabled={!canSend}
              aria-label={t('agent.send')}
              onClick={() => void handleSend()}
            >
              {t('agent.send')}
            </button>
          )}
        </div>
      </footer>
      </div>
    </aside>
  );
}
