import type { ReactNode, SelectHTMLAttributes } from "react";
import { useId } from "react";

import "./DojoControls.css";

export interface DojoSelectOption {
  value: string;
  label: ReactNode;
  disabled?: boolean;
}

export interface DojoSelectProps
  extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "children"> {
  label?: ReactNode;
  options: DojoSelectOption[];
  placeholder?: string;
  fieldClassName?: string;
}

export function DojoSelect({
  className = "",
  fieldClassName = "",
  id,
  label,
  options,
  placeholder,
  ...props
}: DojoSelectProps) {
  const generatedId = useId();
  const selectId = id ?? generatedId;
  const fieldClasses = ["dojo-field", fieldClassName].filter(Boolean).join(" ");
  const selectClasses = ["dojo-select", className].filter(Boolean).join(" ");

  return (
    <label className={fieldClasses} htmlFor={selectId}>
      {label && <span className="dojo-field__label">{label}</span>}
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
    </label>
  );
}
