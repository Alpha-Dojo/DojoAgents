import { useEffect, useRef } from "react";

interface AgentCommandPaletteProps {
  description: string;
  label: string;
  selected: boolean;
  onSelect: () => void;
}

export function AgentCommandPalette({
  description,
  label,
  selected,
  onSelect,
}: AgentCommandPaletteProps) {
  const optionRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (selected) optionRef.current?.scrollIntoView({ block: "nearest" });
  }, [selected]);

  return (
    <div className="dojo-agent-command-palette" role="listbox" aria-label={label}>
      <p className="dojo-agent-command-palette__label">{label}</p>
      <button
        ref={optionRef}
        type="button"
        className={`dojo-agent-command-palette__option${selected ? " is-selected" : ""}`}
        role="option"
        aria-selected={selected}
        onMouseDown={(event) => event.preventDefault()}
        onClick={onSelect}
      >
        <span className="dojo-agent-command-palette__icon" aria-hidden>⌁</span>
        <span className="dojo-agent-command-palette__copy">
          <strong>/status</strong>
          <span>{description}</span>
        </span>
        <kbd>↵</kbd>
      </button>
    </div>
  );
}
