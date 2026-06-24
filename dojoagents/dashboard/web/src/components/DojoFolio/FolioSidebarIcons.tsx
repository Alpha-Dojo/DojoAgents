export function PinIcon({ filled = false }: { filled?: boolean }) {
  return (
    <svg
      className="folio-sidebar__icon-svg"
      viewBox="0 0 16 16"
      aria-hidden
      fill={filled ? 'currentColor' : 'none'}
      stroke="currentColor"
      strokeWidth="1.4"
    >
      <path d="M8 1.5v3.2M5.2 4.7h5.6l-.8 4.2 1.6 1.6-1 1-2.4-2.4-2.4 2.4-1-1 1.6-1.6-.8-4.2z" />
    </svg>
  );
}

export function TrashIcon() {
  return (
    <svg
      className="folio-sidebar__icon-svg"
      viewBox="0 0 16 16"
      aria-hidden
      fill="none"
      stroke="currentColor"
      strokeWidth="1.4"
    >
      <path d="M3.5 4.5h9M6 4.5V3.2h4V4.5M5.2 4.5l.5 8h4.6l.5-8" />
    </svg>
  );
}
