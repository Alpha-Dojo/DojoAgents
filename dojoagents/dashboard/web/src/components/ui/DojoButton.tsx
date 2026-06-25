import type { ButtonHTMLAttributes, ReactNode } from "react";

import "./DojoControls.css";

export type DojoButtonVariant = "primary" | "secondary";
export type DojoControlSize = "xs" | "sm" | "md";

export interface DojoButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode;
  size?: DojoControlSize;
  variant?: DojoButtonVariant;
}

export function DojoButton({
  children,
  className = "",
  size = "md",
  type = "button",
  variant = "primary",
  ...props
}: DojoButtonProps) {
  const classes = [
    "dojo-button",
    `dojo-button--${variant}`,
    `dojo-button--${size}`,
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
