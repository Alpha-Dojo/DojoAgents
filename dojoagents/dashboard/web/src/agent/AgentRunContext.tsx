import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import {
  cancelAgentRun,
  createAgentRun,
  fetchAgentRunStatus,
  streamAgentRunEvents,
} from '../api/agent';
import {
  clearActiveRunDraft,
  clearStreamDraft,
  loadActiveRunDraft,
  loadStreamDraftFull,
  saveActiveRunDraft,
  saveStreamDraft,
} from './agentStorage';
import type { AgentActivityStep, AgentChatMessage, AgentLocale } from '../types/agent';
import {
  appendEvalHint,
  appendThinkDelta,
  appendThinkEnd,
  appendThinkStart,
  appendToolStart,
  finalizeThinkSteps,
  resolveCurrentThinkId,
  resolveToolResult,
  toggleThinkStep,
  toolItemsFromSteps,
} from '../utils/agentActivityTimeline';
import { syncFolioAfterAgentSession, syncFolioFromAgentTool } from '../utils/agentFolioSync';
import { messagesForSessionPersist } from '../utils/agentMessages';
import { persistSessionMessagesSync } from './agentSessionPersist';

export type AgentLivePhase = 'planning' | 'tools' | 'answering' | 'done' | null;

interface InternalRunState {
  sessionId: string;
  runId: string;
  modelId: string;
  draftMessages: AgentChatMessage[];
  assistantText: string;
  assistantSteps: AgentActivityStep[];
  currentThinkId: string | null;
  livePhase: AgentLivePhase;
  retryNotice: string | null;
  error: string | null;
  cursor: number;
  eventCursor: number;
  subscribeAbort: AbortController | null;
  uiLocale: 'zh' | 'en';
  toolsCompleteLabel: string;
  responseCompleteLabel: string;
  stoppedLabel: string;
  formatRetryNotice: (attempt: number, max: number) => string;
  onComplete?: (finalMessages: AgentChatMessage[]) => void;
  onPersistDraft?: (messages: AgentChatMessage[]) => void;
}

export interface SessionRunView {
  running: boolean;
  draftMessages: AgentChatMessage[];
  livePhase: AgentLivePhase;
  retryNotice: string | null;
  error: string | null;
}

interface StartRunParams {
  sessionId: string;
  modelId: string;
  locale: AgentLocale;
  draftMessages: AgentChatMessage[];
  apiMessages: AgentChatMessage[];
  toolsCompleteLabel: string;
  responseCompleteLabel: string;
  stoppedLabel: string;
  uiLocale: 'zh' | 'en';
  formatRetryNotice: (attempt: number, max: number) => string;
  onComplete: (finalMessages: AgentChatMessage[]) => void;
  onPersistDraft?: (messages: AgentChatMessage[]) => void;
}

interface AgentRunContextValue {
  getSessionRun: (sessionId: string | null) => SessionRunView;
  startRun: (params: StartRunParams) => Promise<void>;
  stopRun: (sessionId: string) => Promise<void>;
  isSessionRunning: (sessionId: string | null) => boolean;
  wireRunCallbacks: (
    sessionId: string,
    callbacks: {
      onComplete: (finalMessages: AgentChatMessage[]) => void;
      onPersistDraft?: (messages: AgentChatMessage[]) => void;
    },
  ) => void;
  toggleRunThinkBlock: (sessionId: string, blockId: string) => void;
}

const AgentRunContext = createContext<AgentRunContextValue | null>(null);

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

function emptyView(): SessionRunView {
  return {
    running: false,
    draftMessages: [],
    livePhase: null,
    retryNotice: null,
    error: null,
  };
}

function noopRetry(attempt: number, max: number) {
  return `${attempt}/${max}`;
}

export function AgentRunProvider({ children }: { children: ReactNode }) {
  const runsRef = useRef<Map<string, InternalRunState>>(new Map());
  const subscribeRunRef = useRef<(state: InternalRunState, startCursor: number) => Promise<void>>(
    async () => {},
  );
  const [version, setVersion] = useState(0);
  const notify = useCallback(() => setVersion((value) => value + 1), []);

  const patchRunDraft = useCallback(
    (state: InternalRunState) => {
      state.draftMessages = updateAssistantMessage(state.draftMessages, {
        content: state.assistantText,
        activitySteps: state.assistantSteps,
      });
      state.onPersistDraft?.(state.draftMessages);
      saveStreamDraft({
        sessionId: state.sessionId,
        modelId: state.modelId,
        messages: state.draftMessages,
        updatedAt: Date.now(),
        interrupted: false,
        eventCursor: state.eventCursor,
      });
      saveActiveRunDraft({
        sessionId: state.sessionId,
        runId: state.runId,
        modelId: state.modelId,
        cursor: state.eventCursor,
        updatedAt: Date.now(),
      });
      notify();
    },
    [notify],
  );

  const finishRun = useCallback(
    (state: InternalRunState, finalMessages: AgentChatMessage[]) => {
      runsRef.current.delete(state.sessionId);
      clearActiveRunDraft();
      clearStreamDraft();
      if (state.onComplete) {
        state.onComplete(finalMessages);
      } else {
        persistSessionMessagesSync(state.sessionId, finalMessages, state.modelId);
      }
      notify();
    },
    [notify],
  );

  const finalizeRunFromState = useCallback(
    (state: InternalRunState) => {
      const tools = toolItemsFromSteps(state.assistantSteps);
      syncFolioAfterAgentSession(
        tools.map((item) => ({
          tool: item.tool,
          ok: item.status === 'done',
        })),
      );
      state.livePhase = 'done';
      state.retryNotice = null;
      state.currentThinkId = null;
      state.assistantSteps = finalizeThinkSteps(state.assistantSteps);
      const fallbackContent =
        state.assistantText ||
        (tools.length > 0 ? state.toolsCompleteLabel : state.responseCompleteLabel);
      const base = state.draftMessages.slice(0, -1);
      finishRun(state, [
        ...base,
        {
          role: 'assistant' as const,
          content: fallbackContent,
          activitySteps: state.assistantSteps.length > 0 ? state.assistantSteps : undefined,
        },
      ]);
    },
    [finishRun],
  );

  const continueRunAfterStream = useCallback(
    (state: InternalRunState, status: { status: string; event_count: number }) => {
      state.cursor = status.event_count;
      state.eventCursor = Math.max(state.eventCursor, status.event_count);
      saveActiveRunDraft({
        sessionId: state.sessionId,
        runId: state.runId,
        modelId: state.modelId,
        cursor: state.eventCursor,
        updatedAt: Date.now(),
      });
      if (!runsRef.current.has(state.sessionId)) {
        return;
      }
      if (status.status === 'done' && state.livePhase !== 'done') {
        finalizeRunFromState(state);
        return;
      }
      if (status.status === 'error' || status.status === 'cancelled') {
        if (state.livePhase !== 'done') {
          state.error =
            status.status === 'cancelled' ? state.stoppedLabel : 'Agent run failed';
          state.livePhase = null;
          state.retryNotice = null;
          state.assistantSteps = finalizeThinkSteps(state.assistantSteps);
          const base = state.draftMessages.slice(0, -1);
          finishRun(state, [
            ...base,
            {
              role: 'assistant' as const,
              content: state.assistantText || state.error,
              activitySteps:
                state.assistantSteps.length > 0 ? state.assistantSteps : undefined,
            },
          ]);
        }
        return;
      }
      if (status.status === 'running') {
        void subscribeRunRef.current(state, status.event_count);
      }
    },
    [finalizeRunFromState, finishRun],
  );

  const subscribeRun = useCallback(
    async (state: InternalRunState, startCursor: number) => {
      state.subscribeAbort?.abort();
      const controller = new AbortController();
      state.subscribeAbort = controller;
      state.cursor = startCursor;
      state.eventCursor = startCursor;

      const consumeEvent = (apply: () => void) => {
        apply();
        state.eventCursor += 1;
      };

      const handlers = {
        onPhase: (phase: 'planning' | 'tools' | 'answering') => {
          consumeEvent(() => {
            state.livePhase = phase;
            notify();
          });
        },
        onRetry: ({
          attempt,
          max_attempts,
        }: {
          attempt: number;
          max_attempts: number;
        }) => {
          consumeEvent(() => {
            state.retryNotice = state.formatRetryNotice(attempt, max_attempts);
            state.livePhase = 'planning';
            notify();
          });
        },
        onThinkStart: () => {
          consumeEvent(() => {
            const next = appendThinkStart(state.assistantSteps, state.currentThinkId);
            state.assistantSteps = next.steps;
            state.currentThinkId = next.currentThinkId;
            patchRunDraft(state);
          });
        },
        onThinkDelta: (text: string) => {
          consumeEvent(() => {
            state.assistantSteps = appendThinkDelta(
              state.assistantSteps,
              state.currentThinkId,
              text,
            );
            patchRunDraft(state);
          });
        },
        onThinkEnd: () => {
          consumeEvent(() => {
            state.assistantSteps = appendThinkEnd(state.assistantSteps, state.currentThinkId);
            state.currentThinkId = null;
            patchRunDraft(state);
          });
        },
        onDelta: (text: string) => {
          consumeEvent(() => {
            state.assistantText += text;
            patchRunDraft(state);
          });
        },
        onToolStart: (tool: string, args: Record<string, unknown>, callId?: string) => {
          consumeEvent(() => {
            state.assistantSteps = appendToolStart(state.assistantSteps, tool, args, callId);
            patchRunDraft(state);
          });
        },
        onToolResult: (payload: {
          call_id?: string;
          tool: string;
          ok: boolean;
          latency_ms: number;
          error?: string | null;
          data?: Record<string, unknown> | null;
          viz_blocks?: import('../types/agentViz').AgentVizBlock[];
          resource_changes?: Record<string, unknown>[];
        }) => {
          consumeEvent(() => {
            state.assistantSteps = resolveToolResult(
              state.assistantSteps,
              payload.tool,
              payload.ok,
              payload.latency_ms,
              state.uiLocale,
              payload.error,
              payload.data,
              payload.viz_blocks,
              payload.call_id,
            );
            patchRunDraft(state);
            void syncFolioFromAgentTool(
              payload.tool,
              payload.ok,
              payload.data ?? null,
              payload.resource_changes ?? null,
            );
          });
        },
        onEvalHint: ({ issues }: { issues: string[] }) => {
          consumeEvent(() => {
            state.assistantSteps = appendEvalHint(state.assistantSteps, issues);
            patchRunDraft(state);
          });
        },
        onDone: () => {
          consumeEvent(() => {
            finalizeRunFromState(state);
          });
        },
        onError: (message: string) => {
          consumeEvent(() => {
            const tools = toolItemsFromSteps(state.assistantSteps);
            syncFolioAfterAgentSession(
              tools.map((item) => ({
                tool: item.tool,
                ok: item.status === 'done',
              })),
            );
            state.error = message;
            state.livePhase = null;
            state.retryNotice = null;
            state.assistantSteps = finalizeThinkSteps(state.assistantSteps);
            if (state.assistantText || state.assistantSteps.length > 0) {
              const base = state.draftMessages.slice(0, -1);
              finishRun(state, [
                ...base,
                {
                  role: 'assistant' as const,
                  content: state.assistantText || message,
                  activitySteps:
                    state.assistantSteps.length > 0 ? state.assistantSteps : undefined,
                },
              ]);
            } else {
              runsRef.current.delete(state.sessionId);
              clearActiveRunDraft();
              clearStreamDraft();
              notify();
            }
          });
        },
      };

      try {
        const result = await streamAgentRunEvents(
          state.runId,
          startCursor,
          handlers,
          controller.signal,
        );
        if (
          controller.signal.aborted ||
          result === 'aborted' ||
          !runsRef.current.has(state.sessionId)
        ) {
          return;
        }
        const status = await fetchAgentRunStatus(state.runId);
        continueRunAfterStream(state, status);
      } catch {
        if (!controller.signal.aborted && runsRef.current.has(state.sessionId)) {
          try {
            const status = await fetchAgentRunStatus(state.runId);
            continueRunAfterStream(state, status);
          } catch {
            // ignore reconnect errors
          }
        }
      }
    },
    [continueRunAfterStream, finalizeRunFromState, finishRun, notify, patchRunDraft],
  );

  subscribeRunRef.current = subscribeRun;

  const attachExistingRun = useCallback(
    async (
      sessionId: string,
      runId: string,
      modelId: string,
      draftMessages: AgentChatMessage[],
      cursor: number,
      onComplete: (finalMessages: AgentChatMessage[]) => void,
    ) => {
      if (runsRef.current.has(sessionId)) return;
      const last = draftMessages[draftMessages.length - 1];
      const assistantSteps = last?.role === 'assistant' ? last.activitySteps ?? [] : [];
      const state: InternalRunState = {
        sessionId,
        runId,
        modelId,
        draftMessages,
        assistantText: last?.role === 'assistant' ? last.content : '',
        assistantSteps,
        currentThinkId: resolveCurrentThinkId(assistantSteps),
        livePhase: 'planning',
        retryNotice: null,
        error: null,
        cursor,
        eventCursor: cursor,
        subscribeAbort: null,
        uiLocale: 'zh',
        toolsCompleteLabel: '',
        responseCompleteLabel: '',
        stoppedLabel: '',
        formatRetryNotice: noopRetry,
        onComplete,
      };
      runsRef.current.set(sessionId, state);
      notify();
      void subscribeRun(state, cursor);
    },
    [notify, subscribeRun],
  );

  useEffect(() => {
    const active = loadActiveRunDraft();
    if (!active) return;

    void (async () => {
      const streamDraft = await loadStreamDraftFull(active.sessionId);
      if (!streamDraft || streamDraft.sessionId !== active.sessionId) return;
      try {
        const status = await fetchAgentRunStatus(active.runId);
        if (status.status === 'cancelled') {
          clearActiveRunDraft();
          clearStreamDraft();
          return;
        }
        // streamDraft already reflects events up to eventCursor — only subscribe for new ones
        const resumeCursor = streamDraft.eventCursor ?? active.cursor ?? status.event_count;
        await attachExistingRun(
          active.sessionId,
          active.runId,
          active.modelId,
          streamDraft.messages,
          resumeCursor,
          (finalMessages) => {
            persistSessionMessagesSync(active.sessionId, finalMessages, active.modelId);
          },
        );
      } catch {
        clearActiveRunDraft();
      }
    })();
  }, [attachExistingRun]);

  const startRun = useCallback(
    async (params: StartRunParams) => {
      const existing = runsRef.current.get(params.sessionId);
      if (existing) {
        existing.subscribeAbort?.abort();
        runsRef.current.delete(params.sessionId);
      }

      const { run_id: runId } = await createAgentRun({
        session_id: params.sessionId,
        model_id: params.modelId,
        locale: params.locale,
        messages: params.apiMessages,
      });

      const state: InternalRunState = {
        sessionId: params.sessionId,
        runId,
        modelId: params.modelId,
        draftMessages: params.draftMessages,
        assistantText: '',
        assistantSteps: [],
        currentThinkId: null,
        livePhase: 'planning',
        retryNotice: null,
        error: null,
        cursor: 0,
        eventCursor: 0,
        subscribeAbort: null,
        onComplete: params.onComplete,
        onPersistDraft: params.onPersistDraft,
        uiLocale: params.uiLocale,
        toolsCompleteLabel: params.toolsCompleteLabel,
        responseCompleteLabel: params.responseCompleteLabel,
        stoppedLabel: params.stoppedLabel,
        formatRetryNotice: params.formatRetryNotice,
      };
      runsRef.current.set(params.sessionId, state);
      saveActiveRunDraft({
        sessionId: params.sessionId,
        runId,
        modelId: params.modelId,
        cursor: 0,
        updatedAt: Date.now(),
      });
      saveStreamDraft({
        sessionId: params.sessionId,
        modelId: params.modelId,
        messages: params.draftMessages,
        updatedAt: Date.now(),
        interrupted: false,
      });
      notify();
      await subscribeRun(state, 0);
    },
    [notify, subscribeRun],
  );

  const stopRun = useCallback(
    async (sessionId: string) => {
      const state = runsRef.current.get(sessionId);
      if (!state) return;
      state.subscribeAbort?.abort();
      state.subscribeAbort = null;
      try {
        await cancelAgentRun(state.runId);
      } catch {
        // ignore cancel errors
      }
      const finalMessages = updateAssistantMessage(state.draftMessages, {
        content: state.assistantText || state.stoppedLabel,
        activitySteps: state.assistantSteps.length > 0 ? state.assistantSteps : undefined,
      });
      finishRun(state, messagesForSessionPersist(finalMessages));
    },
    [finishRun],
  );

  const getSessionRun = useCallback(
    (sessionId: string | null): SessionRunView => {
      void version;
      if (!sessionId) return emptyView();
      const state = runsRef.current.get(sessionId);
      if (!state) return emptyView();
      return {
        running: true,
        draftMessages: updateAssistantMessage(state.draftMessages, {
          content: state.assistantText,
          activitySteps: state.assistantSteps,
        }),
        livePhase: state.livePhase,
        retryNotice: state.retryNotice,
        error: state.error,
      };
    },
    [version],
  );

  const isSessionRunning = useCallback(
    (sessionId: string | null) => {
      void version;
      return Boolean(sessionId && runsRef.current.has(sessionId));
    },
    [version],
  );

  const wireRunCallbacks = useCallback(
    (
      sessionId: string,
      callbacks: {
        onComplete: (finalMessages: AgentChatMessage[]) => void;
        onPersistDraft?: (messages: AgentChatMessage[]) => void;
      },
    ) => {
      const state = runsRef.current.get(sessionId);
      if (!state) return;
      state.onComplete = callbacks.onComplete;
      state.onPersistDraft = callbacks.onPersistDraft;
    },
    [],
  );

  const toggleRunThinkBlock = useCallback(
    (sessionId: string, blockId: string) => {
      const state = runsRef.current.get(sessionId);
      if (!state) return;
      const nextSteps = toggleThinkStep(state.assistantSteps, blockId);
      if (nextSteps === state.assistantSteps) return;
      state.assistantSteps = nextSteps;
      patchRunDraft(state);
    },
    [patchRunDraft],
  );

  const value = useMemo(
    () => ({
      getSessionRun,
      startRun,
      stopRun,
      isSessionRunning,
      wireRunCallbacks,
      toggleRunThinkBlock,
    }),
    [getSessionRun, isSessionRunning, startRun, stopRun, toggleRunThinkBlock, wireRunCallbacks],
  );

  return <AgentRunContext.Provider value={value}>{children}</AgentRunContext.Provider>;
}

export function useAgentRun() {
  const context = useContext(AgentRunContext);
  if (!context) {
    throw new Error('useAgentRun must be used within AgentRunProvider');
  }
  return context;
}
