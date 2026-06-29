import { useLayoutEffect, useState, type RefObject } from 'react';

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

/** Fluid full-width layout; scale typography from viewport height only. */
export function useEntityViewportLayout(viewRef: RefObject<HTMLElement | null>): Record<string, string> {
  const [vars, setVars] = useState<Record<string, string>>({});

  useLayoutEffect(() => {
    const view = viewRef.current;
    if (!view) return;

    const update = () => {
      const height = view.clientHeight;
      const width = view.clientWidth;
      if (height <= 0 || width <= 0) return;

      const minScale = width < 520 ? 0.8 : width < 760 ? 0.84 : width < 960 ? 0.88 : 0.9;
      const scale = clamp(Math.min(height / 780, width / 960), minScale, 1.06);
      const gap = Math.max(4, Math.round(6 * scale));

      setVars({
        '--core-scale': String(scale),
        '--core-gap': `${gap}px`,
        '--core-pad-x': `${Math.max(6, Math.round(8 * scale))}px`,
        '--core-title-size': `${Math.round(12 * scale)}px`,
        '--panel-title-size': `${Math.round(12 * scale)}px`,
        '--core-body-size': `${Math.round(11 * scale)}px`,
        '--core-ticker-size': `${Math.round(20 * scale)}px`,
        '--core-price-size': `${Math.round(24 * scale)}px`,
      });
    };

    update();
    const observer = new ResizeObserver(update);
    observer.observe(view);
    window.addEventListener('resize', update);
    return () => {
      observer.disconnect();
      window.removeEventListener('resize', update);
    };
  }, [viewRef]);

  return vars;
}
