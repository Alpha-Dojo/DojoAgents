import type { ReactNode } from 'react';

interface CoreCardProps {
  title?: string;
  className?: string;
  actions?: ReactNode;
  children: ReactNode;
}

export function CoreCard({ title, className, actions, children }: CoreCardProps) {
  const showHead = Boolean(title || actions);

  return (
    <article className={`core-card ${className ?? ''}`.trim()}>
      {showHead ? (
        <header className="core-card__head">
          {title ? <h3 className="core-card__title">{title}</h3> : <span />}
          {actions ? <div className="core-card__actions">{actions}</div> : null}
        </header>
      ) : null}
      <div className="core-card__body">{children}</div>
    </article>
  );
}
