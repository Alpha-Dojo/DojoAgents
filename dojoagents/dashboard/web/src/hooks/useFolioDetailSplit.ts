import { useCallback, useEffect, useRef, useState } from 'react';

const STORAGE_KEY = 'dojo-folio-performance-ratio-v1';
const DEFAULT_RATIO = 0.52;
const MIN_RATIO = 0.28;
const MAX_RATIO = 0.78;
const HANDLE_HEIGHT = 6;
const MIN_DETAIL_HEIGHT = 160;

function clampRatio(value: number): number {
  return Math.min(MAX_RATIO, Math.max(MIN_RATIO, value));
}

function readStoredRatio(): number {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    const parsed = stored ? Number(stored) : Number.NaN;
    if (Number.isFinite(parsed)) return clampRatio(parsed);
  } catch {
    // ignore
  }
  return DEFAULT_RATIO;
}

export function useFolioDetailSplit() {
  const splitRef = useRef<HTMLDivElement>(null);
  const [ratio, setRatio] = useState(readStoredRatio);
  const [resizing, setResizing] = useState(false);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, String(ratio));
    } catch {
      // ignore
    }
  }, [ratio]);

  const onResizeStart = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (event.button !== 0) return;
      event.preventDefault();

      const container = splitRef.current;
      if (!container) return;

      const rect = container.getBoundingClientRect();
      const startY = event.clientY;
      const startRatio = ratio;
      const availableHeight = Math.max(rect.height - HANDLE_HEIGHT, 1);
      setResizing(true);

      const handleMove = (moveEvent: PointerEvent) => {
        const delta = moveEvent.clientY - startY;
        const nextHeight = startRatio * availableHeight + delta;
        const maxRatio = Math.min(
          MAX_RATIO,
          (availableHeight - MIN_DETAIL_HEIGHT) / availableHeight,
        );
        const nextRatio = clampRatio(Math.min(maxRatio, nextHeight / availableHeight));
        setRatio(nextRatio);
      };

      const handleUp = (upEvent: PointerEvent) => {
        const delta = upEvent.clientY - startY;
        const nextHeight = startRatio * availableHeight + delta;
        const maxRatio = Math.min(
          MAX_RATIO,
          (availableHeight - MIN_DETAIL_HEIGHT) / availableHeight,
        );
        setRatio(clampRatio(Math.min(maxRatio, nextHeight / availableHeight)));
        setResizing(false);
        window.removeEventListener('pointermove', handleMove);
        window.removeEventListener('pointerup', handleUp);
        window.removeEventListener('pointercancel', handleUp);
      };

      window.addEventListener('pointermove', handleMove);
      window.addEventListener('pointerup', handleUp);
      window.addEventListener('pointercancel', handleUp);
    },
    [ratio],
  );

  useEffect(() => {
    if (!resizing) return;
    const previousCursor = document.body.style.cursor;
    const previousUserSelect = document.body.style.userSelect;
    document.body.style.cursor = 'row-resize';
    document.body.style.userSelect = 'none';
    return () => {
      document.body.style.cursor = previousCursor;
      document.body.style.userSelect = previousUserSelect;
    };
  }, [resizing]);

  return {
    splitRef,
    ratio,
    resizing,
    onResizeStart,
  };
}
