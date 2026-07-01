import { useEffect } from "react";
import { useTranslation } from "../../hooks/useTranslation";
import type { AgentChatImageAttachment } from "../../types/agent";
import "./AgentImagePreview.css";

interface AgentImagePreviewProps {
  image: AgentChatImageAttachment | null;
  onClose: () => void;
}

export function AgentImagePreview({ image, onClose }: AgentImagePreviewProps) {
  const { t } = useTranslation();

  useEffect(() => {
    if (!image) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [image, onClose]);

  if (!image) return null;

  return (
    <div className="dojo-agent-image-preview" role="presentation">
      <button
        type="button"
        className="dojo-agent-image-preview__scrim"
        aria-label={t("agent.closeImagePreview")}
        onClick={onClose}
      />
      <figure className="dojo-agent-image-preview__figure">
        <button
          type="button"
          className="dojo-agent-image-preview__close"
          aria-label={t("agent.closeImagePreview")}
          onClick={onClose}
        >
          ×
        </button>
        <img
          className="dojo-agent-image-preview__image"
          src={image.dataUrl}
          alt={image.name ?? t("agent.attachedImage")}
        />
        {image.name ? (
          <figcaption className="dojo-agent-image-preview__caption">
            {image.name}
          </figcaption>
        ) : null}
      </figure>
    </div>
  );
}
