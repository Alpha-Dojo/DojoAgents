import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { useAgentModel } from '../../agent/AgentModelContext';
import { useAgentSessions } from '../../agent/useAgentSessions';
import { streamAgentChat } from '../../api/agent';
import { useTranslation } from '../../hooks/useTranslation';
import type { AgentChatMessage } from '../../types/agent';
import { AgentModelSwitcher } from '../AgentModelSwitcher';
import '../AgentModelSwitcher.css';
import './DojoAgentPanel.css';

interface DojoAgentPanelProps {
  open: boolean;
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

export function DojoAgentPanel({ open, onClose }: DojoAgentPanelProps) {
  const { t } = useTranslation();
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
  const [draftMessages, setDraftMessages] = useState<AgentChatMessage[]>([]);
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
      setHistoryOpen(false);
    },
    [activeSessionId, selectSession, sessions, setSelectedModelId],
  );

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || streaming || !geminiConfigured) return;

    const sessionId = ensureActiveSession(selectedModelId);
    const userMessage: AgentChatMessage = { role: 'user', content: text };
    const pendingAssistant: AgentChatMessage = { role: 'assistant', content: '' };
    const nextMessages = [...messages, userMessage, pendingAssistant];

    setDraftMessages(nextMessages);
    setInput('');
    setStreaming(true);
    setError(null);

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    let assistantText = '';

    await streamAgentChat(
      {
        model_id: selectedModelId,
        messages: [...messages, userMessage],
      },
      {
        onDelta: (delta) => {
          assistantText += delta;
          setDraftMessages((prev) => {
            if (prev.length === 0) return prev;
            const updated = [...prev];
            updated[updated.length - 1] = { role: 'assistant', content: assistantText };
            return updated;
          });
        },
        onDone: () => {
          const finalMessages = [
            ...messages,
            userMessage,
            { role: 'assistant' as const, content: assistantText },
          ];
          persistMessages(sessionId, finalMessages);
          setStreaming(false);
          abortRef.current = null;
          textareaRef.current?.focus();
        },
        onError: (message) => {
          setError(message);
          setDraftMessages([]);
          setInput(text);
          setStreaming(false);
          abortRef.current = null;
          textareaRef.current?.focus();
        },
      },
      controller.signal,
    );
  }, [
    ensureActiveSession,
    geminiConfigured,
    input,
    messages,
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

  const canSend = geminiConfigured && input.trim().length > 0 && !streaming;
  const displayMessages =
    draftMessages.length > 0 ? draftMessages : messages;

  return (
    <aside
      id="dojo-agent-panel"
      className={`dojo-agent-panel ${open ? 'dojo-agent-panel--open' : ''}`}
      role="complementary"
      aria-labelledby="dojo-agent-title"
      aria-hidden={!open}
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
        <button
          type="button"
          className="dojo-agent-panel__close"
          aria-label={t('agent.close')}
          onClick={onClose}
        >
          ×
        </button>
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
            if (message.role === 'assistant' && !message.content && !isStreamingAssistant) {
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
                  {message.content}
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
          <button
            type="button"
            className="action-button dojo-agent-panel__send"
            disabled={!canSend}
            aria-label={t('agent.send')}
            onClick={() => void handleSend()}
          >
            {streaming ? t('agent.sending') : t('agent.send')}
          </button>
        </div>
      </footer>
    </aside>
  );
}
