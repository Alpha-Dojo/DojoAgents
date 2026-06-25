import type { InputHTMLAttributes, ReactNode } from "react";
import { useId } from "react";

import "./DojoControls.css";

export interface DojoInputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: ReactNode;
  fieldClassName?: string;
}

export function DojoInput({
  className = "",
  fieldClassName = "",
  id,
  label,
  ...props
}: DojoInputProps) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const fieldClasses = ["dojo-field", fieldClassName].filter(Boolean).join(" ");
  const inputClasses = ["dojo-input", className].filter(Boolean).join(" ");

  return (
    <label className={fieldClasses} htmlFor={inputId}>
      {label && <span className="dojo-field__label">{label}</span>}
      <input className={inputClasses} id={inputId} {...props} />
    </label>
  );
}
