import type { MouseEvent, ReactNode } from 'react';

interface FolioLockableFieldProps {
  locked: boolean;
  lockHint: string;
  unlockHint: string;
  onToggleLock: () => void;
  className?: string;
  children: ReactNode;
}

export function FolioLockableField({
  locked,
  lockHint,
  unlockHint,
  onToggleLock,
  className,
  children,
}: FolioLockableFieldProps) {
  const handleClick = (event: MouseEvent<HTMLDivElement>) => {
    if (!locked) return;
    const target = event.target as HTMLElement;
    if (target.closest('input, select, textarea, button')) return;
    event.preventDefault();
    event.stopPropagation();
    onToggleLock();
  };

  const handleDoubleClick = (event: MouseEvent<HTMLDivElement>) => {
    if (locked) return;
    const target = event.target as HTMLElement;
    if (target.closest('input, select, textarea, button')) return;
    event.preventDefault();
    event.stopPropagation();
    onToggleLock();
  };

  return (
    <div
      className={`folio-lockable${locked ? ' folio-lockable--locked' : ''}${className ? ` ${className}` : ''}`}
      title={locked ? unlockHint : lockHint}
      onClick={handleClick}
      onDoubleClick={handleDoubleClick}
    >
      {children}
    </div>
  );
}
