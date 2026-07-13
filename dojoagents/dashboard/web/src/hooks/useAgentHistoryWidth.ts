import React, { useCallback, useEffect, useState } from 'react';

const STORAGE_KEY = 'dojo-agent-history-width-v1';
const DEFAULT_WIDTH = 240;
const MIN_WIDTH = 180;
const MAX_WIDTH = 480;

function clampWidth(value: number): number {
  return Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, Math.round(value)));
}

function readStoredWidth(): number {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    const parsed = stored ? Number(stored) : Number.NaN;
    if (Number.isFinite(parsed)) return clampWidth(parsed);
  } catch {
    // ignore
  }
  return DEFAULT_WIDTH;
}

export function useAgentHistoryWidth() {
  const [width, setWidth] = useState(readStoredWidth);
  const [resizing, setResizing] = useState(false);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, String(width));
    } catch {
      // ignore
    }
  }, [width]);

  const onResizeStart = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (event.button !== 0) return;
      event.preventDefault();

      const startX = event.clientX;
      const startWidth = width;
      setResizing(true);

      const handleMove = (moveEvent: PointerEvent) => {
        setWidth(clampWidth(startWidth + (moveEvent.clientX - startX)));
      };

      const handleUp = (upEvent: PointerEvent) => {
        setResizing(false);
        setWidth(clampWidth(startWidth + (upEvent.clientX - startX)));
        window.removeEventListener('pointermove', handleMove);
        window.removeEventListener('pointerup', handleUp);
        window.removeEventListener('pointercancel', handleUp);
      };

      window.addEventListener('pointermove', handleMove);
      window.addEventListener('pointerup', handleUp);
      window.addEventListener('pointercancel', handleUp);
    },
    [width],
  );

  useEffect(() => {
    if (!resizing) return;
    const previousCursor = document.body.style.cursor;
    const previousUserSelect = document.body.style.userSelect;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    return () => {
      document.body.style.cursor = previousCursor;
      document.body.style.userSelect = previousUserSelect;
    };
  }, [resizing]);

  return { width, resizing, onResizeStart };
}
