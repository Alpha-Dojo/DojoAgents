import { useEffect, useRef, useState, type ReactNode } from 'react';

interface DropdownMenuProps {
  className: string;
  children: (controls: { close: () => void; open: boolean; toggle: () => void }) => ReactNode;
}

export function DropdownMenu({ className, children }: DropdownMenuProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;

    const handlePointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };

    window.addEventListener('mousedown', handlePointerDown);
    return () => window.removeEventListener('mousedown', handlePointerDown);
  }, [open]);

  return (
    <div className={className} ref={rootRef}>
      {children({
        close: () => setOpen(false),
        open,
        toggle: () => setOpen((prev) => !prev),
      })}
    </div>
  );
}
