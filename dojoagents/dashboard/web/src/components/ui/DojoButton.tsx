import type { ButtonHTMLAttributes, ReactNode } from "react";

import "./DojoControls.css";

export type DojoButtonVariant = "primary" | "secondary" | "error";
export type DojoControlSize = "xs" | "sm" | "md";

export interface DojoButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode;
  icon?: boolean;
  size?: DojoControlSize;
  variant?: DojoButtonVariant;
}

export function DojoButton({
  children,
  className = "",
  icon = false,
  size = "md",
  type = "button",
  variant = "primary",
  ...props
}: DojoButtonProps) {
  const classes = [
    "dojo-button",
    `dojo-button--${variant}`,
    `dojo-button--${size}`,
    icon ? "dojo-button--icon" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <button className={classes} type={type} {...props}>
      {children}
    </button>
  );
}
