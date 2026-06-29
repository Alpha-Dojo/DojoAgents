import type { ReactNode } from 'react';

interface EntityCardProps {
  title?: string;
  className?: string;
  actions?: ReactNode;
  children: ReactNode;
}

export function EntityCard({ title, className, actions, children }: EntityCardProps) {
  const showHead = Boolean(title || actions);

  return (
    <article className={`entity-card ${className ?? ''}`.trim()}>
      {showHead ? (
        <header className="entity-card__head">
          {title ? <h3 className="entity-card__title">{title}</h3> : <span />}
          {actions ? <div className="entity-card__actions">{actions}</div> : null}
        </header>
      ) : null}
      <div className="entity-card__body">{children}</div>
    </article>
  );
}
