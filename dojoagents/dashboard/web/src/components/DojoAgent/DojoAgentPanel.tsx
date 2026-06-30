import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type ClipboardEvent,
  type KeyboardEvent,
} from "react";
import { useAgentModel } from "../../agent/AgentModelContext";
import { useAgentRun } from "../../agent/AgentRunContext";
import {
  AGENT_DRAFT_STORAGE_KEY,
  AGENT_SESSIONS_STORAGE_KEY,
  clearStreamDraft,
  loadStreamDraftFull,
  saveStreamDraft,
} from "../../agent/agentStorage";
import { useAgentSessions } from "../../agent/useAgentSessions";
import { useAgentPanelWidth } from "../../hooks/useAgentPanelWidth";
import { useTranslation } from "../../hooks/useTranslation";
import type { AppTab } from "../../navigation/appTab";
import type { AgentChatImageAttachment, AgentChatMessage } from "../../types/agent";
import { AgentModelSwitcher } from "../AgentModelSwitcher";
import "../AgentModelSwitcher.css";
import { AgentImagePreview } from "./AgentImagePreview";
import { AgentActivityTimeline } from "./AgentActivityTimeline";
import { AgentMarkdown } from "./AgentMarkdown";
import { AgentSuggestedQuestions } from "./AgentSuggestedQuestions";
import {
  resolveActivitySteps,
  toggleThinkStep,
} from "../../utils/agentActivityTimeline";
import {
  attachDerivedVizBlocks,
  collectVizBlocksFromSteps,
  hasRenderedChartBlocks,
  stripRenderedChartBlocks,
} from "../../utils/agentVizContent";
import {
  AGENT_MAX_IMAGE_ATTACHMENTS,
  collectImageFilesFromClipboard,
  createImageAttachmentFromDataUrl,
  createImageAttachmentFromFile,
  extractDataImageUrlFromClipboard,
  mergeImageAttachments,
} from "../../utils/agentImageAttachments";
import {
  finalizeIncompleteAssistantMessages,
  messagesForSessionPersist,
  prepareMessagesForApi,
} from "../../utils/agentMessages";
import "./DojoAgentPanel.css";
import { DojoButton } from "../ui";
import agentIcon from "../../assets/svg/agent.svg";

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
    <svg
      viewBox="0 0 1024 1024"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path
        fill="currentColor"
        d="M512 85.333c235.648 0 426.667 191.019 426.667 426.667S747.648 938.667 512 938.667a424.789 424.789 0 0 1-200.875-50.134L85.333 938.667l50.176-225.707A424.789 424.789 0 0 1 85.333 512C85.333 276.352 276.352 85.333 512 85.333Zm0 85.334C323.477 170.667 170.667 323.477 170.667 512c0 56.96 13.909 111.701 40.106 160.683l14.934 27.904-27.99 125.696 125.782-27.904 27.861 14.89A339.413 339.413 0 0 0 512 853.333 341.333 341.333 0 1 0 512 170.667Zm42.667 128V512h170.666v85.333h-256V298.667h85.334Z"
      />
    </svg>
  );
}
function NewChatIcon() {
  return (
    <svg
      viewBox="0 0 1024 1024"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path
        fill="currentColor"
        d="M333.184 987.456a52.928 52.928 0 0 1-18.688-3.712 47.424 47.424 0 0 1-16.064-10.56 44.544 44.544 0 0 1-10.624-15.36 45.76 45.76 0 0 1-4.032-18.304l-1.088-96.896a256.896 256.896 0 0 1-82.304-27.456 239.808 239.808 0 0 1-36.16-24.128 219.008 219.008 0 0 1-31.488-29.632 265.728 265.728 0 0 1-25.6-34.752 240.384 240.384 0 0 1-30.336-79.744 237.44 237.44 0 0 1-3.648-42.368V346.24c0-15.68 1.472-31.04 4.352-46.4 3.328-15.36 8.064-30.4 13.952-44.992a248.32 248.32 0 0 1 52.992-77.184A242.432 242.432 0 0 1 269.504 112.64a230.4 230.4 0 0 1 47.552-4.736H486.4a44.48 44.48 0 0 1 30.72 12.416 42.176 42.176 0 0 1 0 59.584 43.712 43.712 0 0 1-30.72 12.48H317.056c-10.56 0-20.8 0.704-30.72 2.88-10.24 1.856-20.096 4.8-29.632 8.832a139.904 139.904 0 0 0-27.392 14.208 169.344 169.344 0 0 0-23.808 19.072 171.584 171.584 0 0 0-19.712 23.36 171.008 171.008 0 0 0-14.656 26.688 155.264 155.264 0 0 0-11.712 58.88v258.24c0 10.24 0.768 20.096 2.944 30.336 2.176 9.856 5.12 19.776 9.152 29.248a148.48 148.48 0 0 0 34.752 50.816 155.52 155.52 0 0 0 51.904 33.664c9.536 4.032 19.776 6.976 30.016 9.152 10.24 1.856 20.48 2.944 31.104 2.944a48.896 48.896 0 0 1 34.688 13.888 50.88 50.88 0 0 1 11.008 15.744c2.56 5.824 3.648 12.032 4.032 18.24l0.32 59.648 108.992-77.888c27.84-19.776 58.88-29.632 93.248-29.632h134.976c10.624 0 20.864-1.088 30.72-2.944 10.24-1.856 20.096-4.736 29.632-8.768 9.472-4.032 18.624-8.768 27.392-14.272 8.448-5.504 16.512-12.096 23.808-19.008 7.296-7.296 13.888-14.976 19.712-23.424a145.344 145.344 0 0 0 23.424-55.552c2.176-9.92 2.944-19.776 2.944-30.016V473.216a40.896 40.896 0 0 1 12.8-29.632 44.48 44.48 0 0 1 47.168-9.152c5.12 1.92 9.856 5.12 13.888 9.152a40.896 40.896 0 0 1 12.8 29.632V606.72a233.92 233.92 0 0 1-41.344 132.416 221.184 221.184 0 0 1-30.336 36.16 262.208 262.208 0 0 1-36.928 29.632 229.952 229.952 0 0 1-42.048 21.952 251.712 251.712 0 0 1-93.632 18.304H599.744c-33.984 0-65.088 9.856-92.864 29.632L362.432 977.92a49.92 49.92 0 0 1-29.248 9.536z"
      />
      <path
        fill="currentColor"
        d="M902.592 188.16h-237.44a42.176 42.176 0 0 0 0 84.352h237.44a42.176 42.176 0 1 0 0-84.352z"
      />
      <path
        fill="currentColor"
        d="M827.008 116.288a43.2 43.2 0 0 0-86.336 0v228.096a43.2 43.2 0 0 0 86.4 0V116.288z"
      />
    </svg>
  );
}

function PanelSizeIcon({ maximized }: { maximized: boolean }) {
  return maximized ? (
    <svg
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <g clipPath="url(#clip0_43081_3490)">
        <path
          d="M23.0013 0.999023H0.998535V23.0018H23.0013V0.999023Z"
          stroke="currentColor"
          strokeWidth="1.99723"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d="M8.07227 4.51021V8.20508H4.3774"
          stroke="currentColor"
          strokeWidth="1.99723"
          strokeMiterlimit="10"
        />
        <path
          d="M15.9279 4.51021V8.20508H19.6228"
          stroke="currentColor"
          strokeWidth="1.99723"
          strokeMiterlimit="10"
        />
        <path
          d="M8.07227 19.4893V15.7944H4.3774"
          stroke="currentColor"
          strokeWidth="1.99723"
          strokeMiterlimit="10"
        />
        <path
          d="M15.9279 19.4893V15.7944H19.6228"
          stroke="currentColor"
          strokeWidth="1.99723"
          strokeMiterlimit="10"
        />
      </g>
      <defs>
        <clipPath id="clip0_43081_3490">
          <rect width="24" height="24" fill="white" />
        </clipPath>
      </defs>
    </svg>
  ) : (
    <svg
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <g clipPath="url(#clip0_43081_3479)">
        <path
          d="M23.0013 0.999023H0.998535V23.0018H23.0013V0.999023Z"
          stroke="currentColor"
          strokeWidth="1.99723"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d="M4.37744 8.20463V4.50977H8.07231"
          stroke="currentColor"
          strokeWidth="1.99723"
          strokeMiterlimit="10"
        />
        <path
          d="M19.6228 8.20463V4.50977H15.928"
          stroke="currentColor"
          strokeWidth="1.99723"
          strokeMiterlimit="10"
        />
        <path
          d="M4.37744 15.7939V19.4888H8.07231"
          stroke="currentColor"
          strokeWidth="1.99723"
          strokeMiterlimit="10"
        />
        <path
          d="M19.6228 15.7939V19.4888H15.928"
          stroke="currentColor"
          strokeWidth="1.99723"
          strokeMiterlimit="10"
        />
      </g>
      <defs>
        <clipPath id="clip0_43081_3479">
          <rect width="24" height="24" fill="white" />
        </clipPath>
      </defs>
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg
      className="dojo-agent-panel__toolbar-icon"
      viewBox="0 0 16 16"
      aria-hidden
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
    >
      <path d="m3 3 10 10M13 3 3 13" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <path
        d="M16.1792 4.95996V2.98047H16.3999C16.2789 2.98047 16.1792 2.88077 16.1792 2.75977V2.98047H7.81982V2.75977C7.81982 2.88077 7.72012 2.98047 7.59912 2.98047H7.81982V4.95996H16.1792ZM5.30322 6.94043L5.96924 21.0195H18.0308L18.6958 6.94043H5.30322ZM21.6802 4.95996C22.1667 4.96014 22.56 5.35329 22.5601 5.83984V6.71973C22.5601 6.84073 22.4604 6.94043 22.3394 6.94043H20.6792L19.9995 21.3223C19.9555 22.2627 19.183 22.9998 18.2427 23H5.75732C4.81962 23 4.04449 22.26 4.00049 21.3223L3.3208 6.94043H1.65967C1.53879 6.94028 1.43994 6.84064 1.43994 6.71973V5.83984C1.44003 5.35321 1.83319 4.96002 2.31982 4.95996H5.83936V2.75977C5.83948 1.78926 6.62865 1.00023 7.59912 1H16.3999C17.3704 1.00022 18.1595 1.78926 18.1597 2.75977V4.95996H21.6802Z"
        fill="currentColor"
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
    sessionsHydrated,
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
  const [pendingImages, setPendingImages] = useState<AgentChatImageAttachment[]>([]);
  const [imageAttaching, setImageAttaching] = useState(false);
  const [previewImage, setPreviewImage] = useState<AgentChatImageAttachment | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [maximized, setMaximized] = useState(false);
  const [switchingSessionId, setSwitchingSessionId] = useState<string | null>(
    null,
  );
  const [recoveredNotice, setRecoveredNotice] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const stickToBottomRef = useRef(true);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
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
    let cancelled = false;
    void (async () => {
      const draft = await loadStreamDraftFull();
      if (cancelled || !draft?.interrupted) return;
      const finalized = finalizeIncompleteAssistantMessages(
        draft.messages,
        t("agent.interrupted"),
      );
      replaceSessionMessages(draft.sessionId, finalized, draft.modelId);
      selectSession(draft.sessionId);
      setRecoveredNotice(true);
      clearStreamDraft();
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- recover once on mount
  }, []);

  useEffect(() => {
    if (!recoveredNotice) return;
    const timer = window.setTimeout(() => setRecoveredNotice(false), 12000);
    return () => window.clearTimeout(timer);
  }, [recoveredNotice]);

  useEffect(() => {
    const container = messagesContainerRef.current;
    if (!container) return;

    const onScroll = () => {
      const distance =
        container.scrollHeight - container.scrollTop - container.clientHeight;
      stickToBottomRef.current = distance <= 96;
    };

    container.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    return () => container.removeEventListener("scroll", onScroll);
  }, [activeSessionId, open]);

  useEffect(() => {
    if (!stickToBottomRef.current) return;
    messagesEndRef.current?.scrollIntoView({
      behavior: streaming ? "auto" : "smooth",
    });
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
    if (open || pinned) return;
    setMaximized(false);
  }, [open, pinned]);

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
    setPendingImages([]);
    setHistoryOpen(false);
    setRecoveredNotice(false);
    stickToBottomRef.current = true;
    clearStreamDraft();
    createSession(selectedModelId);
  }, [createSession, selectedModelId]);

  const handleSelectSession = useCallback(
    (sessionId: string) => {
      if (sessionId === activeSessionId) {
        setHistoryOpen(false);
        return;
      }
      stickToBottomRef.current = true;
      setSwitchingSessionId(sessionId);
      setError(null);
      setInput("");
      setPendingImages([]);
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

  const addImageFiles = useCallback(
    async (files: Array<{ file: File; mimeHint?: string }>) => {
      if (files.length === 0 || streaming || imageAttaching) return false;
      setImageAttaching(true);
      setError(null);
      const nextAttachments: AgentChatImageAttachment[] = [];
      try {
        for (const entry of files) {
          if (pendingImages.length + nextAttachments.length >= AGENT_MAX_IMAGE_ATTACHMENTS) {
            break;
          }
          try {
            nextAttachments.push(
              await createImageAttachmentFromFile(entry.file, entry.mimeHint),
            );
          } catch (err) {
            setError(err instanceof Error ? err.message : t("agent.imageAttachFailed"));
          }
        }
        if (nextAttachments.length === 0) return false;
        setPendingImages((current) => mergeImageAttachments(current, nextAttachments));
        setError(null);
        textareaRef.current?.focus();
        return true;
      } finally {
        setImageAttaching(false);
      }
    },
    [imageAttaching, pendingImages.length, streaming, t],
  );

  const addImageDataUrl = useCallback(
    async (dataUrl: string) => {
      if (streaming || imageAttaching) return false;
      if (pendingImages.length >= AGENT_MAX_IMAGE_ATTACHMENTS) {
        setError(t("agent.imageAttachFailed"));
        return false;
      }
      setImageAttaching(true);
      setError(null);
      try {
        const attachment = await createImageAttachmentFromDataUrl(dataUrl);
        setPendingImages((current) => mergeImageAttachments(current, [attachment]));
        setError(null);
        textareaRef.current?.focus();
        return true;
      } catch (err) {
        setError(err instanceof Error ? err.message : t("agent.imageAttachFailed"));
        return false;
      } finally {
        setImageAttaching(false);
      }
    },
    [imageAttaching, pendingImages.length, streaming, t],
  );

  const handlePaste = useCallback(
    (event: ClipboardEvent<HTMLTextAreaElement>) => {
      const dataUrl = extractDataImageUrlFromClipboard(event.clipboardData);
      const files = collectImageFilesFromClipboard(event.clipboardData);
      if (!dataUrl && files.length === 0) return;

      event.preventDefault();
      void (async () => {
        if (dataUrl) {
          const attached = await addImageDataUrl(dataUrl);
          if (!attached) {
            setError(t("agent.imagePasteFailed"));
          }
          return;
        }
        const attached = await addImageFiles(files);
        if (!attached) {
          setError(t("agent.imagePasteFailed"));
        }
      })();
    },
    [addImageDataUrl, addImageFiles, t],
  );

  const handleImageInputChange = useCallback(
    (event: ChangeEvent<HTMLInputElement>) => {
      const files = Array.from(event.target.files ?? []).map((file) => ({ file }));
      event.target.value = "";
      void addImageFiles(files);
    },
    [addImageFiles],
  );

  const handleRemovePendingImage = useCallback((index: number) => {
    setPendingImages((current) => current.filter((_, itemIndex) => itemIndex !== index));
  }, []);

  const handleSend = useCallback(async () => {
    const text = input.trim();
    const images = pendingImages;
    if (!sessionsHydrated) {
      setError(t("agent.sendBlockedNotReady"));
      return;
    }
    if (streaming) {
      setError(t("agent.sendBlockedStreaming"));
      return;
    }
    if (imageAttaching) {
      setError(t("agent.imageAttaching"));
      return;
    }
    if (!selectedModel?.available) {
      setError(t("agent.apiNotConfigured"));
      return;
    }
    if (!text && images.length === 0) {
      setError(t("agent.sendRequiresInput"));
      return;
    }

    const sessionId = ensureActiveSession(selectedModelId);
    const userMessage: AgentChatMessage = {
      role: "user",
      content: text,
      ...(images.length > 0 ? { images } : {}),
    };
    const pendingAssistant: AgentChatMessage = {
      role: "assistant",
      content: "",
      activitySteps: [],
    };
    const nextMessages = [...messages, userMessage, pendingAssistant];
    const apiMessages = prepareMessagesForApi(
      [...messages, userMessage],
      t("agent.toolsComplete"),
    );
    if (apiMessages.length === 0) {
      setError(t("agent.sendEmptyPayload"));
      return;
    }
    const uiLocale = locale === "zh" ? "zh" : "en";

    setInput("");
    setPendingImages([]);
    setError(null);
    stickToBottomRef.current = true;
    replaceSessionMessages(
      sessionId,
      [...messages, userMessage],
      selectedModelId,
    );

    try {
      await startRun({
        sessionId,
        modelId: selectedModelId,
        locale,
        dashboardTab: sourceTab,
        draftMessages: nextMessages,
        apiMessages,
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
        onRunError: (message) => {
          setError(message);
        },
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("agent.sendFailed"));
      setInput(text);
      setPendingImages(images);
    }
  }, [
    ensureActiveSession,
    locale,
    messages,
    pendingImages,
    persistMessages,
    replaceSessionMessages,
    schedulePersistDraft,
    sessionsHydrated,
    selectedModel?.available,
    input,
    startRun,
    streaming,
    imageAttaching,
    selectedModelId,
    t,
  ]);

  const handleStop = useCallback(() => {
    if (!streaming || !activeSessionId) return;
    void stopRun(activeSessionId);
    textareaRef.current?.focus();
  }, [activeSessionId, stopRun, streaming]);

  const canSend =
    sessionsHydrated &&
    Boolean(selectedModel?.available) &&
    (input.trim().length > 0 || pendingImages.length > 0) &&
    !streaming &&
    !imageAttaching;

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (!canSend) {
        if (!input.trim() && pendingImages.length === 0) {
          setError(t("agent.sendRequiresInput"));
        } else if (streaming) {
          setError(t("agent.sendBlockedStreaming"));
        } else if (imageAttaching) {
          setError(t("agent.imageAttaching"));
        } else if (!sessionsHydrated) {
          setError(t("agent.sendBlockedNotReady"));
        } else if (!selectedModel?.available) {
          setError(t("agent.apiNotConfigured"));
        }
        return;
      }
      void handleSend();
    }
  };

  const showSendHint =
    !streaming &&
    Boolean(selectedModel?.available) &&
    sessionsHydrated &&
    !canSend;
  const displayMessages = messages;
  const maximizeLabel = t(maximized ? "agent.minimize" : "agent.maximize");

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
  const panelMaximized = isOpen && maximized;

  return (
    <aside
      id="dojo-agent-panel"
      className={`dojo-agent-panel ${isOpen ? "dojo-agent-panel--open" : ""}${
        pinned ? " dojo-agent-panel--pinned" : ""
      }${interactive ? " dojo-agent-panel--interactive" : ""}${
        resizing ? " dojo-agent-panel--resizing" : ""
      }${panelMaximized ? " dojo-agent-panel--maximized" : ""}`}
      style={
        isOpen ? (maximized ? undefined : { width: panelWidth }) : undefined
      }
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
            <img
              src={agentIcon}
              alt=""
              className="dojo-agent-panel__title-icon"
              aria-hidden
            />
            DojoAgent
          </h2>
          <div className="dojo-agent-panel__head-actions">
            <DojoButton
              icon
              size="xs"
              variant="secondary"
              className={`${historyOpen ? "is-active" : ""}`}
              aria-expanded={historyOpen}
              aria-label={t("agent.history")}
              title={t("agent.history")}
              onClick={() => setHistoryOpen((prev) => !prev)}
            >
              <HistoryIcon />
            </DojoButton>
            <DojoButton
              icon
              size="xs"
              variant="secondary"
              aria-label={t("agent.newChat")}
              title={t("agent.newChat")}
              onClick={handleNewSession}
            >
              <NewChatIcon />
            </DojoButton>
            <DojoButton
              icon
              size="xs"
              variant="secondary"
              className="mini-icon"
              aria-pressed={maximized}
              aria-label={maximizeLabel}
              title={maximizeLabel}
              onClick={() => setMaximized((prev) => !prev)}
            >
              <PanelSizeIcon maximized={maximized} />
            </DojoButton>
            {!pinned ? (
              <DojoButton
                icon
                size="xs"
                variant="error"
                className="mini-icon"
                aria-label={t("agent.close")}
                title={t("agent.close")}
                onClick={onClose}
              >
                <CloseIcon />
              </DojoButton>
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
                        <DojoButton
                          icon
                          size="xs"
                          variant="error"
                          className="dojo-agent-panel__history-delete"
                          aria-label={t("agent.deleteSession")}
                          disabled={isLoading}
                          onClick={() => deleteSession(session.id)}
                        >
                          <TrashIcon />
                        </DojoButton>
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
            ref={messagesContainerRef}
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
              const rawActivitySteps = resolveActivitySteps(message);
              const activitySteps =
                message.role === "assistant"
                  ? attachDerivedVizBlocks(rawActivitySteps)
                  : rawActivitySteps;
              const hasActivity = activitySteps.length > 0;
              const messageVizBlocks =
                message.role === "assistant"
                  ? collectVizBlocksFromSteps(activitySteps)
                  : [];
              const displayContent =
                message.role === "assistant"
                  ? stripRenderedChartBlocks(
                      message.content,
                      hasRenderedChartBlocks(messageVizBlocks),
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
                      <>
                        {message.images && message.images.length > 0 ? (
                          <div className="dojo-agent-panel__user-images">
                            {message.images.map((image, imageIndex) => (
                              <button
                                key={`${image.dataUrl.slice(0, 32)}-${imageIndex}`}
                                type="button"
                                className="dojo-agent-panel__user-image-btn"
                                aria-label={t("agent.previewImage")}
                                onClick={() => setPreviewImage(image)}
                              >
                                <img
                                  className="dojo-agent-panel__user-image"
                                  src={image.dataUrl}
                                  alt={image.name ?? t("agent.attachedImage")}
                                />
                              </button>
                            ))}
                          </div>
                        ) : null}
                        {message.content ? (
                          <p className="dojo-agent-panel__user-text">{message.content}</p>
                        ) : null}
                      </>
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
                        {displayContent ? (
                          <AgentMarkdown
                            content={displayContent}
                            streaming={isStreamingAssistant && !!displayContent}
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
          {pendingImages.length > 0 || imageAttaching ? (
            <div className="dojo-agent-panel__attachment-list" aria-label={t("agent.pendingImages")}>
              {imageAttaching ? (
                <div
                  className="dojo-agent-panel__attachment dojo-agent-panel__attachment--loading"
                  aria-live="polite"
                  aria-busy="true"
                >
                  <div className="dojo-agent-panel__loading-spinner" />
                  <span className="dojo-agent-panel__attachment-loading-label">
                    {t("agent.imageAttaching")}
                  </span>
                </div>
              ) : null}
              {pendingImages.map((image, index) => (
                <div key={`${image.dataUrl.slice(0, 32)}-${index}`} className="dojo-agent-panel__attachment">
                  <button
                    type="button"
                    className="dojo-agent-panel__attachment-preview-btn"
                    aria-label={t("agent.previewImage")}
                    onClick={() => setPreviewImage(image)}
                  >
                    <img
                      className="dojo-agent-panel__attachment-preview"
                      src={image.dataUrl}
                      alt={image.name ?? t("agent.attachedImage")}
                    />
                  </button>
                  <button
                    type="button"
                    className="dojo-agent-panel__attachment-remove"
                    aria-label={t("agent.removeImage")}
                    disabled={streaming}
                    onClick={() => handleRemovePendingImage(index)}
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          ) : null}
          <textarea
            ref={textareaRef}
            className="dojo-agent-panel__input"
            rows={3}
            value={input}
            placeholder={t("agent.placeholder")}
            disabled={!selectedModel?.available || streaming || imageAttaching}
            onChange={(event) => setInput(event.target.value)}
            onPaste={handlePaste}
            onKeyDown={handleKeyDown}
          />
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            multiple
            hidden
            onChange={handleImageInputChange}
          />
          <div className="dojo-agent-panel__composer-bar">
            <div className="dojo-agent-panel__composer-left">
              <AgentModelSwitcher variant="composer" />
              <DojoButton
                variant="secondary"
                size="xs"
                className={
                  pendingImages.length > 0
                    ? "dojo-agent-panel__attach-btn dojo-agent-panel__attach-btn--active"
                    : "dojo-agent-panel__attach-btn"
                }
                disabled={
                  !selectedModel?.available ||
                  streaming ||
                  imageAttaching ||
                  pendingImages.length >= AGENT_MAX_IMAGE_ATTACHMENTS
                }
                aria-label={t("agent.attachImage")}
                aria-busy={imageAttaching}
                onClick={() => fileInputRef.current?.click()}
              >
                {imageAttaching ? (
                  t("agent.imageAttaching")
                ) : pendingImages.length > 0 ? (
                  t("agent.attachedImageCount", { count: pendingImages.length })
                ) : (
                  t("agent.attachImage")
                )}
              </DojoButton>
            </div>
            {streaming ? (
              <DojoButton
                variant="secondary"
                size="xs"
                className="dojo-agent-panel__send-btn"
                aria-label={t("agent.stop")}
                onClick={handleStop}
              >
                {t("agent.stop")}
              </DojoButton>
            ) : (
              <DojoButton
                variant="secondary"
                size="xs"
                className="dojo-agent-panel__send-btn"
                disabled={!canSend}
                aria-label={t("agent.send")}
                title={showSendHint ? t("agent.sendRequiresInput") : undefined}
                onClick={() => void handleSend()}
              >
                {t("agent.send")}
              </DojoButton>
            )}
          </div>
          {showSendHint ? (
            <p className="dojo-agent-panel__composer-hint">{t("agent.sendRequiresInput")}</p>
          ) : null}
        </footer>
        <AgentImagePreview
          image={previewImage}
          onClose={() => setPreviewImage(null)}
        />
      </div>
    </aside>
  );
}
