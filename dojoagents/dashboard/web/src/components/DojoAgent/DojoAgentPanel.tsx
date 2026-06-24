import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { useAgentModel } from '../../agent/AgentModelContext';
import { useAgentSessions } from '../../agent/useAgentSessions';
import { streamAgentChat } from '../../api/agent';
import { useTranslation } from '../../hooks/useTranslation';
import { useLocaleContext } from '../../i18n/LocaleContext';
import { invalidateCachePrefix } from '../../cache/queryCache';
import type {
  AgentChatMessage,
  AgentToolActivityItem,
  DojoToolResultEvent,
  DojoToolStartEvent,
  ToolCall,
} from '../../types/agent';
import { AgentModelSwitcher } from '../AgentModelSwitcher';
import '../AgentModelSwitcher.css';
import { AgentMarkdown } from './AgentMarkdown';
import { AgentToolActivity } from './AgentToolActivity';
import './DojoAgentPanel.css';

interface DojoAgentPanelProps {
  open: boolean;
  pinned?: boolean;
  interactive?: boolean;
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

function mergeToolCalls(
  activity: AgentToolActivityItem[] | undefined,
  toolCalls: ToolCall[] | undefined,
): AgentToolActivityItem[] {
  const next = [...(activity ?? [])];
  for (const toolCall of toolCalls ?? []) {
    const existing = next.find((item) => item.id === toolCall.id);
    const args = toolCall.function.arguments || '';
    if (existing) {
      existing.arguments = args;
      existing.tool = toolCall.function.name || existing.tool;
      if (existing.status === 'done') existing.status = 'running';
      continue;
    }
    next.push({
      id: toolCall.id,
      tool: toolCall.function.name || 'tool',
      arguments: args,
      status: 'running',
    });
  }
  return next;
}

function finalizeToolCalls(
  activity: AgentToolActivityItem[] | undefined,
  status: 'done' | 'error',
  error?: string | null,
): AgentToolActivityItem[] {
  return (activity ?? []).map((item) =>
    item.status === 'running'
      ? {
          ...item,
          status,
          error: status === 'error' ? error ?? null : null,
        }
      : item,
  );
}

function appendUnique(values: string[] | undefined, nextValue: string): string[] {
  const next = [...(values ?? [])];
  if (!next.includes(nextValue)) next.push(nextValue);
  return next;
}

function applyToolResult(
  activity: AgentToolActivityItem[] | undefined,
  event: DojoToolResultEvent,
): AgentToolActivityItem[] {
  const next = [...(activity ?? [])];
  const existing = next.find((item) => item.id === event.call_id);
  const patch: AgentToolActivityItem = {
    id: event.call_id,
    tool: event.tool,
    status: event.ok ? 'done' : 'error',
    error: event.ok ? null : event.error || null,
    result: event.ok ? event.content : event.error,
    latencyMs: event.latency_ms,
    data: event.data,
    vizBlocks: event.viz_blocks,
    resourceChanges: event.resource_changes,
  };
  if (existing) {
    Object.assign(existing, patch);
  } else {
    next.push(patch);
  }
  return next;
}

function invalidateResourceChanges(activity: AgentToolActivityItem[]) {
  for (const item of activity) {
    for (const change of item.resourceChanges ?? []) {
      if (change.resource === 'portfolio') {
        invalidateCachePrefix('folio-');
      }
    }
  }
}

export function DojoAgentPanel({
  open,
  pinned = false,
  interactive = false,
  onClose,
}: DojoAgentPanelProps) {
  const { t } = useTranslation();
  const { locale } = useLocaleContext();
  const { selectedModelId, setSelectedModelId } = useAgentModel();
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
  const [draftMessages, setDraftMessages] = useState<AgentChatMessage[]>([]);
  const [switchingSessionId, setSwitchingSessionId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const messages = activeSession?.messages ?? draftMessages;

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streaming, draftMessages]);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  const persistMessages = useCallback(
    (sessionId: string, nextMessages: AgentChatMessage[]) => {
      replaceSessionMessages(sessionId, nextMessages, selectedModelId);
      setDraftMessages([]);
    },
    [replaceSessionMessages, selectedModelId],
  );

  const persistDraft = useCallback(
    (sessionId: string, nextMessages: AgentChatMessage[]) => {
      setDraftMessages(nextMessages);
      replaceSessionMessages(sessionId, nextMessages, selectedModelId);
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
    setDraftMessages([]);
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
    if (!text || streaming) return;

    const sessionId = ensureActiveSession(selectedModelId);
    const userMessage: AgentChatMessage = { role: 'user', content: text };
    const pendingAssistant: AgentChatMessage = {
      role: 'assistant',
      content: '',
      toolActivity: [],
    };
    const nextMessages = [...messages, userMessage, pendingAssistant];

    persistDraft(sessionId, nextMessages);
    setInput('');
    setStreaming(true);
    setError(null);

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    let assistantText = '';
    let assistantTools: AgentToolActivityItem[] = [];
    let assistantPhase: AgentChatMessage['phase'] = 'planning';
    let assistantPhaseHistory: AgentChatMessage['phaseHistory'] = ['planning'];
    let assistantRetries: string[] = [];
    let assistantEvalHints: string[] = [];

    await streamAgentChat(
      {
        model: selectedModelId,
        messages: [...messages, userMessage].map((message) => ({
          role: message.role,
          content: message.content,
        })),
        user: 'dashboard',
        metadata: {
          session_id: sessionId,
          channel: 'dashboard',
          locale,
          history: messages.map((message) => ({
            role: message.role,
            content: message.content,
          })),
        },
      },
      {
        onEvent: (event) => {
          if (event.type === 'content_delta') {
            assistantText += event.content ?? '';
            persistDraft(
              sessionId,
              updateAssistantMessage([...messages, userMessage, pendingAssistant], {
                content: assistantText,
                toolActivity: assistantTools,
                phase: 'answering',
                phaseHistory: appendUnique(assistantPhaseHistory, 'answering') as AgentChatMessage['phaseHistory'],
                retries: assistantRetries,
                evalHints: assistantEvalHints,
              }),
            );
            assistantPhase = 'answering';
            assistantPhaseHistory = appendUnique(assistantPhaseHistory, 'answering') as AgentChatMessage['phaseHistory'];
            return;
          }

          if (event.type === 'tool_call_delta') {
            assistantTools = mergeToolCalls(
              assistantTools,
              event.chunk?.choices[0]?.delta.tool_calls,
            );
            persistDraft(
              sessionId,
              updateAssistantMessage([...messages, userMessage, pendingAssistant], {
                content: assistantText,
                toolActivity: assistantTools,
                phase: 'tools',
                phaseHistory: appendUnique(assistantPhaseHistory, 'tools') as AgentChatMessage['phaseHistory'],
                retries: assistantRetries,
                evalHints: assistantEvalHints,
              }),
            );
            assistantPhase = 'tools';
            assistantPhaseHistory = appendUnique(assistantPhaseHistory, 'tools') as AgentChatMessage['phaseHistory'];
            return;
          }

          if (event.type === 'dojo_event' && event.dojoEvent) {
            const dojoEvent = event.dojoEvent;
            if (dojoEvent.type === 'phase') {
              const phaseEvent = dojoEvent as Extract<typeof dojoEvent, { type: 'phase' }>;
              assistantPhase = phaseEvent.phase;
              assistantPhaseHistory = appendUnique(assistantPhaseHistory, phaseEvent.phase) as AgentChatMessage['phaseHistory'];
            }
            if (dojoEvent.type === 'retry') {
              const retryEvent = dojoEvent as Extract<typeof dojoEvent, { type: 'retry' }>;
              const label = retryEvent.text || `Retry ${retryEvent.attempt}/${retryEvent.max_attempts}`;
              assistantRetries = appendUnique(assistantRetries, label);
            }
            if (dojoEvent.type === 'eval_hint') {
              const evalEvent = dojoEvent as Extract<typeof dojoEvent, { type: 'eval_hint' }>;
              assistantEvalHints = appendUnique(assistantEvalHints, evalEvent.text);
            }
            if (dojoEvent.type === 'tool_start') {
              const toolEvent = dojoEvent as DojoToolStartEvent;
              assistantTools = mergeToolCalls(assistantTools, [
                {
                  id: toolEvent.call_id,
                  type: 'function',
                  function: {
                    name: toolEvent.tool,
                    arguments: JSON.stringify(toolEvent.arguments ?? {}),
                  },
                },
              ]);
            }
            if (dojoEvent.type === 'tool_result') {
              assistantTools = applyToolResult(assistantTools, dojoEvent as DojoToolResultEvent);
              invalidateResourceChanges(assistantTools);
            }
            if (dojoEvent.type === 'error') {
              const errorEvent = dojoEvent as Extract<typeof dojoEvent, { type: 'error' }>;
              setError(errorEvent.message);
            }
            persistDraft(
              sessionId,
              updateAssistantMessage([...messages, userMessage, pendingAssistant], {
                content: assistantText,
                toolActivity: assistantTools,
                phase: assistantPhase,
                phaseHistory: assistantPhaseHistory,
                retries: assistantRetries,
                evalHints: assistantEvalHints,
              }),
            );
            return;
          }

          if (event.type === 'done') {
            const finalMessages = [
              ...messages,
              userMessage,
              {
                role: 'assistant' as const,
                content: assistantText,
                phase: assistantPhase,
                phaseHistory: assistantPhaseHistory,
                retries: assistantRetries,
                evalHints: assistantEvalHints,
                toolActivity: assistantTools.length > 0 ? assistantTools : undefined,
              },
            ];
            persistMessages(sessionId, finalMessages);
            setStreaming(false);
            abortRef.current = null;
            textareaRef.current?.focus();
          }
        },
        onError: (message) => {
          assistantTools = finalizeToolCalls(assistantTools, 'error', message);
          setError(message);
          persistDraft(
            sessionId,
            updateAssistantMessage([...messages, userMessage, pendingAssistant], {
              content: assistantText,
              toolActivity: assistantTools,
              phase: assistantPhase,
              phaseHistory: assistantPhaseHistory,
              retries: assistantRetries,
              evalHints: assistantEvalHints,
            }),
          );
          if (!controller.signal.aborted) {
            setInput(text);
          }
          setStreaming(false);
          abortRef.current = null;
          textareaRef.current?.focus();
        },
      },
      controller.signal,
    );
  }, [
    ensureActiveSession,
    input,
    locale,
    messages,
    persistDraft,
    persistMessages,
    selectedModelId,
    streaming,
  ]);

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      void handleSend();
    }
  };

  const canSend = input.trim().length > 0 && !streaming;
  const displayMessages = draftMessages.length > 0 ? draftMessages : messages;
  const isOpen = pinned || open;

  return (
    <aside
      id="dojo-agent-panel"
      className={`dojo-agent-panel ${isOpen ? 'dojo-agent-panel--open' : ''}${
        pinned ? ' dojo-agent-panel--pinned' : ''
      }${interactive ? ' dojo-agent-panel--interactive' : ''}`}
      role="complementary"
      aria-labelledby="dojo-agent-title"
      aria-hidden={!isOpen}
    >
      <header className="dojo-agent-panel__head">
        <div className="dojo-agent-panel__head-main">
          <div className="dojo-agent-panel__head-actions">
            <button
              type="button"
              className={`dojo-agent-panel__icon-btn ${historyOpen ? 'dojo-agent-panel__icon-btn--active' : ''}`}
              aria-expanded={historyOpen}
              aria-label={t('agent.history')}
              onClick={() => setHistoryOpen((prev) => !prev)}
            >
              ☰
            </button>
            <button
              type="button"
              className="dojo-agent-panel__icon-btn"
              aria-label={t('agent.newChat')}
              onClick={handleNewSession}
            >
              +
            </button>
          </div>
          <div>
            <h2 id="dojo-agent-title" className="dojo-agent-panel__title">
              DojoAgent
            </h2>
            <p className="dojo-agent-panel__sub">{t('agent.subtitle')}</p>
          </div>
        </div>
        {!pinned ? (
          <button
            type="button"
            className="dojo-agent-panel__close"
            aria-label={t('agent.close')}
            onClick={onClose}
          >
            ×
          </button>
        ) : null}
      </header>

      {historyOpen && (
        <div className="dojo-agent-panel__history" role="navigation" aria-label={t('agent.history')}>
          {sessions.length === 0 ? (
            <p className="dojo-agent-panel__history-empty">{t('agent.noHistory')}</p>
          ) : (
            <ul className="dojo-agent-panel__history-list">
              {sessions.map((session) => (
                <li key={session.id}>
                  <div
                    className={`dojo-agent-panel__history-item ${
                      session.id === activeSessionId ? 'dojo-agent-panel__history-item--active' : ''
                    }`}
                  >
                    <button
                      type="button"
                      className="dojo-agent-panel__history-select"
                      disabled={switchingSessionId === session.id}
                      onClick={() => handleSelectSession(session.id)}
                    >
                      <span className="dojo-agent-panel__history-title">
                        {session.title || t('agent.newChatTitle')}
                      </span>
                      <span className="dojo-agent-panel__history-meta">
                        {formatSessionTime(session.updatedAt)}
                      </span>
                    </button>
                    <button
                      type="button"
                      className="dojo-agent-panel__history-delete"
                      aria-label={t('agent.deleteSession')}
                      onClick={() => deleteSession(session.id)}
                    >
                      ×
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="dojo-agent-panel__body">
        <div className="dojo-agent-panel__messages" role="log" aria-live="polite">
          {displayMessages.length === 0 && (
            <p className="dojo-agent-panel__empty">{t('agent.empty')}</p>
          )}
          {displayMessages.map((message, index) => {
            const isStreamingAssistant =
              streaming &&
              message.role === 'assistant' &&
              index === displayMessages.length - 1;
            const toolActivity = message.toolActivity ?? [];
            const hasToolActivity = toolActivity.length > 0;
            const showThinking =
              isStreamingAssistant && !message.content && !hasToolActivity;
            const showAssistantBubble =
              message.role === 'assistant' &&
              (message.content || hasToolActivity || showThinking || isStreamingAssistant);

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
                      <AgentToolActivity
                        items={toolActivity}
                        thinking={showThinking}
                        phase={message.phase}
                        retries={message.retries}
                        evalHints={message.evalHints}
                      />
                      {message.content ? (
                        <AgentMarkdown content={message.content} streaming={isStreamingAssistant} />
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
        {error && <p className="dojo-agent-panel__error">{error}</p>}
        <textarea
          ref={textareaRef}
          className="dojo-agent-panel__input"
          value={input}
          placeholder={t('agent.placeholder')}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={handleKeyDown}
          disabled={switchingSessionId !== null}
        />
        <div className="dojo-agent-panel__composer-bar">
          <AgentModelSwitcher />
          <button
            type="button"
            className="action-button dojo-agent-panel__send"
            disabled={!canSend && !streaming}
            aria-label={streaming ? t('agent.stop') : t('agent.send')}
            onClick={() => {
              if (streaming) {
                abortRef.current?.abort();
                abortRef.current = null;
                setStreaming(false);
                return;
              }
              void handleSend();
            }}
          >
            {streaming ? t('agent.stop') : t('agent.send')}
          </button>
        </div>
      </footer>
    </aside>
  );
}
