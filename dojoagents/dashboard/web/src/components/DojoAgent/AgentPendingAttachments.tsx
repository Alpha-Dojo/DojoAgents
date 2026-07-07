import type { AgentChatImageAttachment, AgentSessionInputFile } from '../../types/agent';
import { useTranslation } from '../../hooks/useTranslation';
import { attachmentKindIcon } from '../../utils/agentAttachmentRouting';
import { formatBytesLabel } from '../../utils/sessionOutputFiles';

interface AgentPendingAttachmentsProps {
  images: AgentChatImageAttachment[];
  files: AgentSessionInputFile[];
  busy?: boolean;
  busyLabel?: string;
  disabled?: boolean;
  onPreviewImage?: (image: AgentChatImageAttachment) => void;
  onRemoveImage: (index: number) => void;
  onRemoveFile: (index: number) => void;
}

export function AgentPendingAttachments({
  images,
  files,
  busy = false,
  busyLabel,
  disabled = false,
  onPreviewImage,
  onRemoveImage,
  onRemoveFile,
}: AgentPendingAttachmentsProps) {
  const { t, locale } = useTranslation();
  const uiLocale = locale === 'zh' ? 'zh' : 'en';

  if (!busy && images.length === 0 && files.length === 0) {
    return null;
  }

  return (
    <div className="dojo-agent-panel__attachment-list" aria-label={t('agent.pendingAttachments')}>
      {busy ? (
        <div
          className="dojo-agent-panel__attachment dojo-agent-panel__attachment--loading"
          aria-live="polite"
          aria-busy="true"
        >
          <div className="dojo-agent-panel__loading-spinner" />
          <span className="dojo-agent-panel__attachment-loading-label">
            {busyLabel ?? t('agent.attachmentAttaching')}
          </span>
        </div>
      ) : null}
      {images.map((image, index) => (
        <div key={`${image.dataUrl.slice(0, 32)}-${index}`} className="dojo-agent-panel__attachment">
          <button
            type="button"
            className="dojo-agent-panel__attachment-preview-btn"
            aria-label={t('agent.previewImage')}
            onClick={() => onPreviewImage?.(image)}
          >
            <img
              className="dojo-agent-panel__attachment-preview"
              src={image.dataUrl}
              alt={image.name ?? t('agent.attachedImage')}
            />
          </button>
          <button
            type="button"
            className="dojo-agent-panel__attachment-remove"
            aria-label={t('agent.removeImage')}
            disabled={disabled}
            onClick={() => onRemoveImage(index)}
          >
            ×
          </button>
        </div>
      ))}
      {files.map((file, index) => (
        <div key={`${file.filename}-${file.path}`} className="dojo-agent-panel__attachment dojo-agent-panel__attachment--file">
          <div className="dojo-agent-panel__attachment-file-card">
            <span className="dojo-agent-panel__attachment-file-icon" aria-hidden>
              {attachmentKindIcon(file.kind)}
            </span>
            <span className="dojo-agent-panel__attachment-file-meta">
              <span className="dojo-agent-panel__attachment-file-name">{file.filename}</span>
              <span className="dojo-agent-panel__attachment-file-size">
                {formatBytesLabel(file.bytes, uiLocale)}
              </span>
            </span>
          </div>
          <button
            type="button"
            className="dojo-agent-panel__attachment-remove"
            aria-label={t('agent.removeFile')}
            disabled={disabled}
            onClick={() => onRemoveFile(index)}
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
}
