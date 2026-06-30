import { useRef, useState } from 'react';
import { createPortal } from 'react-dom';

interface FolioHoldingNameCellProps {
  name: string;
}

function isTextTruncated(element: HTMLElement): boolean {
  if (element.scrollWidth > element.clientWidth + 1) {
    return true;
  }

  const range = document.createRange();
  range.selectNodeContents(element);
  const contentWidth = range.getBoundingClientRect().width;
  const visibleWidth = element.getBoundingClientRect().width;
  if (contentWidth > visibleWidth + 1) {
    return true;
  }

  const cell = element.closest('td');
  if (cell) {
    const cellWidth = cell.getBoundingClientRect().width;
    if (contentWidth > cellWidth + 1) {
      return true;
    }
  }

  return false;
}

export function FolioHoldingNameCell({ name }: FolioHoldingNameCellProps) {
  const textRef = useRef<HTMLSpanElement>(null);
  const [tooltip, setTooltip] = useState<{ x: number; y: number } | null>(null);

  const showTooltip = () => {
    const el = textRef.current;
    if (!el || !name.trim() || !isTextTruncated(el)) return;
    const rect = el.getBoundingClientRect();
    setTooltip({ x: rect.left, y: rect.top - 6 });
  };

  return (
    <td className="folio-table__name">
      <span
        ref={textRef}
        className="folio-table__name-text"
        onMouseEnter={showTooltip}
        onMouseLeave={() => setTooltip(null)}
        onFocus={showTooltip}
        onBlur={() => setTooltip(null)}
        tabIndex={0}
      >
        {name}
      </span>
      {tooltip
        ? createPortal(
            <div
              className="folio-table__name-tooltip"
              style={{ left: tooltip.x, top: tooltip.y }}
              role="tooltip"
            >
              {name}
            </div>,
            document.body,
          )
        : null}
    </td>
  );
}
