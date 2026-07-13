import {
  useCallback,
  useEffect,
  useState,
  type CSSProperties,
  type MouseEvent,
  type RefObject,
} from 'react';
import {
  checkpointTickWidth,
  type AgentConversationCheckpoint,
} from '../../utils/agentConversationCheckpoints';

interface AgentConversationCheckpointsProps {
  checkpoints: AgentConversationCheckpoint[];
  containerRef: RefObject<HTMLDivElement | null>;
  getMessageElement: (messageIndex: number) => HTMLDivElement | null;
  ariaLabel: string;
}

export function AgentConversationCheckpoints({
  checkpoints,
  containerRef,
  getMessageElement,
  ariaLabel,
}: AgentConversationCheckpointsProps) {
  const [activeCheckpointId, setActiveCheckpointId] = useState<string | null>(
    null,
  );
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const [focusedIndex, setFocusedIndex] = useState<number | null>(null);
  const interactiveIndex = focusedIndex ?? hoveredIndex;
  const interactiveCheckpoint =
    interactiveIndex === null ? null : checkpoints[interactiveIndex] ?? null;

  const updateActiveCheckpoint = useCallback(() => {
    const container = containerRef.current;
    if (!container || checkpoints.length === 0) {
      setActiveCheckpointId(null);
      return;
    }

    const containerRect = container.getBoundingClientRect();
    const containerMidpoint = containerRect.top + containerRect.height / 2;
    let nearestId: string | null = null;
    let nearestDistance = Number.POSITIVE_INFINITY;

    checkpoints.forEach((checkpoint) => {
      const target = getMessageElement(checkpoint.userMessageIndex);
      if (!target) return;
      const targetRect = target.getBoundingClientRect();
      const targetMidpoint = targetRect.top + targetRect.height / 2;
      const distance = Math.abs(targetMidpoint - containerMidpoint);
      if (distance < nearestDistance) {
        nearestDistance = distance;
        nearestId = checkpoint.id;
      }
    });

    setActiveCheckpointId(nearestId);
  }, [checkpoints, containerRef, getMessageElement]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    updateActiveCheckpoint();
    container.addEventListener('scroll', updateActiveCheckpoint, {
      passive: true,
    });
    window.addEventListener('resize', updateActiveCheckpoint);

    return () => {
      container.removeEventListener('scroll', updateActiveCheckpoint);
      window.removeEventListener('resize', updateActiveCheckpoint);
    };
  }, [containerRef, updateActiveCheckpoint]);

  const activateCheckpoint = (checkpoint: AgentConversationCheckpoint) => {
    const reduceMotion = window.matchMedia(
      '(prefers-reduced-motion: reduce)',
    ).matches;
    getMessageElement(checkpoint.userMessageIndex)?.scrollIntoView({
      behavior: reduceMotion ? 'auto' : 'smooth',
      block: "start",
    });
  };

  const handleCheckpointClick = (
    event: MouseEvent<HTMLButtonElement>,
    checkpoint: AgentConversationCheckpoint,
  ) => {
    activateCheckpoint(checkpoint);
    setHoveredIndex(null);
    setFocusedIndex(null);
    event.currentTarget.blur();
  };

  if (checkpoints.length <= 5) return null;

  return (
    <nav
      className="agent-conversation-checkpoints"
      aria-label={ariaLabel}
      data-interacting={interactiveIndex !== null ? 'true' : undefined}
      onMouseLeave={() => setHoveredIndex(null)}
    >
      <ol className="agent-conversation-checkpoints__list">
        {checkpoints.map((checkpoint, index) => {
          const isActive = checkpoint.id === activeCheckpointId;
          const isInteractive = index === interactiveIndex;
          const distance =
            interactiveIndex === null
              ? Number.POSITIVE_INFINITY
              : Math.abs(index - interactiveIndex);
          const width = checkpointTickWidth(distance);
          return (
            <li
              key={checkpoint.id}
              className="agent-conversation-checkpoints__item"
              data-interactive={isInteractive ? 'true' : undefined}
              style={
                {
                  '--checkpoint-tick-width': `${width}px`,
                } as CSSProperties
              }
              onMouseEnter={() => setHoveredIndex(index)}
            >
              <button
                type="button"
                className="agent-conversation-checkpoints__tick"
                aria-label={checkpoint.title}
                aria-current={isActive ? "location" : undefined}
                onFocus={() => setFocusedIndex(index)}
                onBlur={() => setFocusedIndex(null)}
                onClick={(event) => handleCheckpointClick(event, checkpoint)}
              >
                <span className="agent-conversation-checkpoints__tick-line" />
              </button>
            </li>
          );
        })}
      </ol>
      {interactiveCheckpoint && interactiveIndex !== null ? (
        <div
          className="agent-conversation-checkpoints__preview"
          role="tooltip"
          style={{ top: `${14 * interactiveIndex + 14}px` }}
        >
          <strong>{interactiveCheckpoint.title}</strong>
          <span>{interactiveCheckpoint.preview}</span>
        </div>
      ) : null}
    </nav>
  );
}
