import type { ReactNode, SelectHTMLAttributes } from "react";
import { useId } from "react";

import type { DojoControlSize } from "./DojoButton";
import "./DojoControls.css";

export interface DojoSelectOption {
  value: string;
  label: ReactNode;
  disabled?: boolean;
}

export interface DojoSelectProps
  extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "children" | "size"> {
  label?: ReactNode;
  options: DojoSelectOption[];
  placeholder?: string;
  fieldClassName?: string;
  size?: DojoControlSize;
}

export function DojoSelect({
  className = "",
  fieldClassName = "",
  id,
  label,
  options,
  placeholder,
  size = "md",
  ...props
}: DojoSelectProps) {
  const generatedId = useId();
  const selectId = id ?? generatedId;
  const fieldClasses = ["dojo-field", `dojo-field--${size}`, fieldClassName]
    .filter(Boolean)
    .join(" ");
  const selectClasses = ["dojo-select", `dojo-select--${size}`, className]
    .filter(Boolean)
    .join(" ");
  const selectControl = (
    <span className="dojo-select-shell">
      <select className={selectClasses} id={selectId} {...props}>
        {placeholder && (
          <option disabled value="">
            {placeholder}
          </option>
        )}
        {options.map((option) => (
          <option
            disabled={option.disabled}
            key={option.value}
            value={option.value}
          >
            {option.label}
          </option>
        ))}
      </select>
      <span className="dojo-select-shell__chevron" aria-hidden="true">
        <svg viewBox="0 0 16 16" width="16" height="16">
          <path
            d="M4 6l4 4 4-4"
            fill="none"
            stroke="currentColor"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="1.5"
          />
        </svg>
      </span>
    </span>
  );

  if (!label) {
    return selectControl;
  }

  return (
    <label className={fieldClasses} htmlFor={selectId}>
      <span className="dojo-field__label">{label}</span>
      {selectControl}
    </label>
  );
}
