import type { InputHTMLAttributes, ReactNode } from "react";
import { useId } from "react";

import type { DojoControlSize } from "./DojoButton";
import "./DojoControls.css";

export interface DojoInputProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, "size"> {
  label?: ReactNode;
  fieldClassName?: string;
  size?: DojoControlSize;
}

export function DojoInput({
  className = "",
  fieldClassName = "",
  id,
  label,
  size = "md",
  ...props
}: DojoInputProps) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const fieldClasses = ["dojo-field", `dojo-field--${size}`, fieldClassName]
    .filter(Boolean)
    .join(" ");
  const inputClasses = ["dojo-input", `dojo-input--${size}`, className]
    .filter(Boolean)
    .join(" ");

  if (!label) {
    return <input className={inputClasses} id={inputId} {...props} />;
  }

  return (
    <label className={fieldClasses} htmlFor={inputId}>
      <span className="dojo-field__label">{label}</span>
      <input className={inputClasses} id={inputId} {...props} />
    </label>
  );
}
