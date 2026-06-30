import type { ReactNode } from 'react';

import './LoadingIndicator.css';

export type LoadingIndicatorVariant = 'inline' | 'panel' | 'page';

interface LoadingIndicatorProps {
  className?: string;
  label?: ReactNode;
  variant?: LoadingIndicatorVariant;
}

export function LoadingIndicator({
  className = '',
  label,
  variant = 'panel',
}: LoadingIndicatorProps) {
  const classes = [
    'dojo-loading',
    `dojo-loading--${variant}`,
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div className={classes} role="status" aria-live="polite">
      <span className="dojo-loading__spinner" aria-hidden="true">
        <span className="dojo-loading__orbit" />
        <span className="dojo-loading__core" />
      </span>
      {label ? <span className="dojo-loading__label">{label}</span> : null}
    </div>
  );
}
