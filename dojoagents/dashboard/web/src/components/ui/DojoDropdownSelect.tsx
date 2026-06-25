import type { CSSProperties } from "react";
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import "./DojoDropdownSelect.css";

export interface DojoDropdownSelectOption {
  value: string;
  label: string;
  detail?: string;
}

interface DojoDropdownSelectProps {
  "aria-label": string;
  className?: string;
  dropdownMinWidth?: number;
  options: DojoDropdownSelectOption[];
  value: string;
  onChange: (value: string) => void;
}

function ChevronIcon() {
  return (
    <svg
      className="dojo-dropdown-select__chevron"
      viewBox="0 0 24 24"
      width="12"
      height="12"
      aria-hidden
    >
      <path
        d="M6 9l6 6 6-6"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.75"
      />
    </svg>
  );
}

export function DojoDropdownSelect({
  "aria-label": ariaLabel,
  className = "",
  dropdownMinWidth,
  options,
  value,
  onChange,
}: DojoDropdownSelectProps) {
  const [open, setOpen] = useState(false);
  const [dropdownStyle, setDropdownStyle] = useState<CSSProperties>({});
  const rootRef = useRef<HTMLDivElement>(null);
  const dropdownRef = useRef<HTMLUListElement>(null);
  const selectedOption = options.find((option) => option.value === value);

  const updateDropdownPosition = useCallback(() => {
    const rect = rootRef.current?.getBoundingClientRect();
    if (!rect) return;

    const minWidth = Math.max(rect.width, dropdownMinWidth ?? 0);
    const viewportPadding = 8;
    const left = Math.max(
      viewportPadding,
      Math.min(rect.left, window.innerWidth - minWidth - viewportPadding),
    );

    setDropdownStyle({
      left,
      minWidth,
      top: rect.bottom + 6,
    });
  }, [dropdownMinWidth]);

  useEffect(() => {
    if (!open) return;

    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (
        !rootRef.current?.contains(target) &&
        !dropdownRef.current?.contains(target)
      ) {
        setOpen(false);
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    const handleViewportChange = () => updateDropdownPosition();

    updateDropdownPosition();
    window.addEventListener("mousedown", handlePointerDown);
    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("resize", handleViewportChange);
    window.addEventListener("scroll", handleViewportChange, true);
    return () => {
      window.removeEventListener("mousedown", handlePointerDown);
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("resize", handleViewportChange);
      window.removeEventListener("scroll", handleViewportChange, true);
    };
  }, [open, updateDropdownPosition]);

  const selectOption = (nextValue: string) => {
    onChange(nextValue);
    setOpen(false);
  };

  const dropdown = open
    ? createPortal(
        <ul
          className="dojo-dropdown-select__dropdown"
          role="listbox"
          aria-label={ariaLabel}
          ref={dropdownRef}
          style={dropdownStyle}
        >
          {options.map((option) => (
            <li key={option.value} role="presentation">
              <button
                type="button"
                role="option"
                aria-selected={value === option.value}
                className={`dojo-dropdown-select__option${
                  value === option.value
                    ? " dojo-dropdown-select__option--active"
                    : ""
                }`}
                onClick={() => selectOption(option.value)}
              >
                <span className="dojo-dropdown-select__option-label">
                  {option.label}
                </span>
                {option.detail && (
                  <span className="dojo-dropdown-select__option-detail">
                    {option.detail}
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>,
        document.body,
      )
    : null;

  return (
    <div
      className={[
        "dojo-dropdown-select",
        open ? "dojo-dropdown-select--open" : "",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      ref={rootRef}
    >
      <button
        type="button"
        className={`dojo-dropdown-select__trigger${
          open ? " dojo-dropdown-select__trigger--open" : ""
        }`}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={ariaLabel}
        onClick={() => setOpen((prev) => !prev)}
      >
        <span className="dojo-dropdown-select__value">
          {selectedOption?.label ?? value}
        </span>
        <ChevronIcon />
      </button>
      {dropdown}
    </div>
  );
}
