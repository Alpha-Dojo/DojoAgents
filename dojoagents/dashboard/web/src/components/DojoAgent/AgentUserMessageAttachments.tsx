import { useMemo, useState } from 'react';
import { revealSessionInput } from '../../api/agent';
import { parseApiErrorMessage } from '../../api/http';
import { useTranslation } from '../../hooks/useTranslation';
import type { AgentChatImageAttachment, AgentSessionInputFile } from '../../types/agent';
import {
  AGENT_ATTACHMENT_COLLAPSE_THRESHOLD,
  attachmentKindIcon,
} from '../../utils/agentAttachmentRouting';
import { formatBytesLabel } from '../../utils/sessionOutputFiles';

interface AgentUserMessageAttachmentsProps {
  images?: AgentChatImageAttachment[];
  files?: AgentSessionInputFile[];
  sessionId?: string | null;
  onPreviewImage?: (image: AgentChatImageAttachment) => void;
}

export function AgentUserMessageAttachments({
  images = [],
  files = [],
  sessionId = null,
  onPreviewImage,
}: AgentUserMessageAttachmentsProps) {
  const { locale, t } = useTranslation();
  const uiLocale = locale === 'zh' ? 'zh' : 'en';
  const [expanded, setExpanded] = useState(false);
  const [copiedPath, setCopiedPath] = useState<string | null>(null);

  const items = useMemo(
    () => [
      ...images.map((image, index) => ({
        key: `image-${image.dataUrl.slice(0, 24)}-${index}`,
        kind: 'image' as const,
        image,
      })),
      ...files.map((file) => ({
        key: `file-${file.filename}-${file.path}`,
        kind: 'file' as const,
        file,
      })),
    ],
    [files, images],
  );

  if (items.length === 0) {
    return null;
  }

  const shouldCollapse = items.length > AGENT_ATTACHMENT_COLLAPSE_THRESHOLD;
  const visibleItems =
    shouldCollapse && !expanded ? items.slice(0, AGENT_ATTACHMENT_COLLAPSE_THRESHOLD - 1) : items;
  const hiddenCount = items.length - visibleItems.length;

  const copyPath = async (path: string) => {
    try {
      await navigator.clipboard.writeText(path);
      setCopiedPath(path);
      window.setTimeout(() => setCopiedPath((current) => (current === path ? null : current)), 2000);
    } catch {
      setCopiedPath(null);
    }
  };

  const revealFile = async (filename: string) => {
    if (!sessionId) return;
    try {
      await revealSessionInput(sessionId, filename);
    } catch (err) {
      console.error(parseApiErrorMessage(err, t('agent.revealFailed')));
    }
  };

  return (
    <div className="dojo-agent-user-attachments" aria-label={t('agent.messageAttachments')}>
      <div className="dojo-agent-user-attachments__grid">
        {visibleItems.map((item) => {
          if (item.kind === 'image') {
            return (
              <button
                key={item.key}
                type="button"
                className="dojo-agent-user-attachments__image-btn"
                aria-label={t('agent.previewImage')}
                onClick={() => onPreviewImage?.(item.image)}
              >
                <img
                  className="dojo-agent-user-attachments__image"
                  src={item.image.dataUrl}
                  alt={item.image.name ?? t('agent.attachedImage')}
                />
              </button>
            );
          }
          const file = item.file;
          const sizeLabel =
            typeof file.bytes === 'number' ? formatBytesLabel(file.bytes, uiLocale) : null;
          return (
            <button
              key={item.key}
              type="button"
              className="dojo-agent-user-attachments__file"
              title={file.path}
              onClick={(event) => {
                if ((event.metaKey || event.ctrlKey) && sessionId) {
                  void revealFile(file.filename);
                  return;
                }
                void copyPath(file.path);
              }}
            >
              <span className="dojo-agent-user-attachments__file-icon" aria-hidden>
                {attachmentKindIcon(file.kind)}
              </span>
              <span className="dojo-agent-user-attachments__file-meta">
                <span className="dojo-agent-user-attachments__file-name">{file.filename}</span>
                {sizeLabel ? (
                  <span className="dojo-agent-user-attachments__file-size">{sizeLabel}</span>
                ) : null}
              </span>
              <span className="dojo-agent-user-attachments__file-action">
                {copiedPath === file.path ? t('agent.pathCopied') : t('agent.copyPath')}
              </span>
            </button>
          );
        })}
      </div>
      {shouldCollapse ? (
        <button
          type="button"
          className="dojo-agent-user-attachments__toggle"
          aria-expanded={expanded}
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded
            ? t('agent.collapseAttachments')
            : t('agent.expandAttachments', { count: hiddenCount })}
        </button>
      ) : null}
    </div>
  );
}
