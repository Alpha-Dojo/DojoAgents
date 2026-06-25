import type { ButtonHTMLAttributes, ReactNode } from "react";

import "./DojoControls.css";

export type DojoButtonVariant = "primary" | "secondary";

export interface DojoButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode;
  variant?: DojoButtonVariant;
}

export function DojoButton({
  children,
  className = "",
  type = "button",
  variant = "primary",
  ...props
}: DojoButtonProps) {
  const classes = ["dojo-button", `dojo-button--${variant}`, className]
    .filter(Boolean)
    .join(" ");

  return (
    <button className={classes} type={type} {...props}>
      {children}
    </button>
  );
}
