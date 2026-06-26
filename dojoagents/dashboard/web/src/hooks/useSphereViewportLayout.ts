import { useLayoutEffect, useState, type RefObject } from 'react';

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

/** Scale analytics panels from the view size; table keeps fixed compact typography. */
export function useSphereScale(viewRef: RefObject<HTMLElement | null>): Record<string, string> {
  const [scaleVars, setScaleVars] = useState<Record<string, string>>({});

  useLayoutEffect(() => {
    const view = viewRef.current;
    if (!view) return;

    const update = () => {
      const height = view.clientHeight;
      const width = view.clientWidth;
      if (height <= 0 || width <= 0) return;

      const minScale = width < 520 ? 0.82 : width < 760 ? 0.86 : width < 960 ? 0.9 : 0.94;
      const scale = clamp(Math.min(height / 820, width / 1320), minScale, 1.12);
      const cardPad = Math.round(10 * scale);
      const gaugeHeight = clamp(Math.round(height * 0.058), 36, 56);
      const gaugeWidth = clamp(Math.round(gaugeHeight * 2.1), 72, 112);
      const radarSize = clamp(Math.round(height * 0.155), 84, 128);

      setScaleVars({
        '--sphere-scale': String(scale),
        '--sphere-card-pad': `${cardPad}px`,
        '--sphere-gauge-h': `${gaugeHeight}px`,
        '--sphere-gauge-w': `${gaugeWidth}px`,
        '--sphere-radar-size': `${radarSize}px`,
        '--sphere-title-size': `${Math.round(12 * scale)}px`,
        '--panel-title-size': `${Math.round(12 * scale)}px`,
        '--sphere-body-size': `${Math.round(12 * scale)}px`,
        '--sphere-table-size': `${Math.max(10, Math.round(11 * scale))}px`,
        '--sphere-table-head-size': `${Math.max(10, Math.round(10 * scale))}px`,
        '--sphere-table-row-pad-y': `${Math.max(3, Math.round(4 * scale))}px`,
        '--sphere-table-row-pad-x': `${Math.max(5, Math.round(5 * scale))}px`,
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

  return scaleVars;
}
