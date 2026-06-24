export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export function formatPeAxis(value: number): string {
  if (!Number.isFinite(value)) return '—';
  return value.toFixed(2);
}

export function formatPriceAxis(value: number): string {
  if (!Number.isFinite(value)) return '—';
  if (Math.abs(value) >= 1) {
    return value.toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }
  return value.toFixed(4);
}

export function formatVolumeCompact(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return '—';
  if (value >= 1e8) return `${(value / 1e8).toFixed(2)}亿`;
  if (value >= 1e4) return `${(value / 1e4).toFixed(2)}万`;
  return value.toFixed(0);
}

export function formatFinancialAmount(value: number, locale: 'zh' | 'en' = 'zh'): string {
  if (!Number.isFinite(value)) return '—';
  const abs = Math.abs(value);
  const sign = value < 0 ? '-' : '';
  if (locale === 'zh') {
    if (abs >= 1e8) return `${sign}${(abs / 1e8).toFixed(1)}亿`;
    if (abs >= 1e4) return `${sign}${(abs / 1e4).toFixed(1)}万`;
    return `${sign}${abs.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
  }
  if (abs >= 1e12) return `${sign}${(abs / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `${sign}${(abs / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `${sign}${(abs / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${sign}${(abs / 1e3).toFixed(1)}K`;
  return `${sign}${abs.toFixed(0)}`;
}

export function formatSignedPercent(value: number, digits = 1): string {
  if (!Number.isFinite(value)) return '—';
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toFixed(digits)}%`;
}

export function priceTickValues(min: number, max: number, count = 5): number[] {
  if (count <= 1) return [min];
  const step = (max - min) / (count - 1);
  return Array.from({ length: count }, (_, i) => min + step * i);
}

export function valueFromChartY(
  y: number,
  min: number,
  max: number,
  height: number,
  padTop: number,
  padBottom: number = padTop,
): number {
  if (height <= padTop + padBottom + 1 || max <= min) return min;
  const ratio = (height - padBottom - y) / (height - padTop - padBottom);
  const value = min + ratio * (max - min);
  return Number.isFinite(value) ? value : min;
}

export function niceMinMax(values: number[], padRatio = 0.08): { min: number; max: number } {
  if (values.length === 0) return { min: 0, max: 1 };
  let min = Math.min(...values);
  let max = Math.max(...values);
  if (min === max) {
    min -= 1;
    max += 1;
  }
  const pad = (max - min) * padRatio;
  return { min: min - pad, max: max + pad };
}

export function movingAverage(values: number[], window: number): Array<number | null> {
  return values.map((_, i) => {
    if (i + 1 < window) return null;
    const slice = values.slice(i + 1 - window, i + 1);
    return slice.reduce((a, b) => a + b, 0) / window;
  });
}

export function formatCompactNumber(value: number, digits = 2): string {
  return value.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function chartX(index: number, count: number, width: number, padX: number): number {
  if (count <= 1) return padX;
  return padX + (index / (count - 1)) * (width - padX * 2);
}

export function candleSlot(
  index: number,
  count: number,
  plotW: number,
  plotX0: number,
): { cx: number; barW: number; slot: number } {
  if (count <= 0) return { cx: plotX0, barW: 4, slot: plotW };
  const slot = plotW / count;
  const cx = plotX0 + (index + 0.5) * slot;
  const barW = clamp(slot * 0.72, 1.5, 14);
  return { cx, barW, slot };
}

export function chartY(
  value: number,
  min: number,
  max: number,
  height: number,
  padTop: number,
  padBottom: number = padTop,
): number {
  if (!Number.isFinite(value) || !Number.isFinite(min) || !Number.isFinite(max)) {
    return height / 2;
  }
  if (height <= padTop + padBottom + 1 || max <= min) {
    return height / 2;
  }
  const ratio = (value - min) / (max - min);
  const y = height - padBottom - ratio * (height - padTop - padBottom);
  return Number.isFinite(y) ? y : height / 2;
}

export function polarPoint(
  cx: number,
  cy: number,
  radius: number,
  angleRad: number,
): { x: number; y: number } {
  return {
    x: cx + radius * Math.sin(angleRad),
    y: cy - radius * Math.cos(angleRad),
  };
}
