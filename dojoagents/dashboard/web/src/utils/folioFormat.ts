export function buildSparklinePath(
  values: number[],
  width: number,
  height: number,
  padX = 2,
  padY = 2,
): string {
  if (values.length < 2) return '';

  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const plotW = width - padX * 2;
  const plotH = height - padY * 2;

  return values
    .map((value, index) => {
      const x = padX + (index / (values.length - 1)) * plotW;
      const y = padY + plotH - ((value - min) / span) * plotH;
      return `${index === 0 ? 'M' : 'L'}${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(' ');
}

export function buildLinePath(
  values: number[],
  width: number,
  height: number,
  yMin: number,
  yMax: number,
  padX = 8,
  padY = 8,
): string {
  if (values.length < 2) return '';

  const span = yMax - yMin || 1;
  const plotW = width - padX * 2;
  const plotH = height - padY * 2;

  return values
    .map((value, index) => {
      const x = padX + (index / (values.length - 1)) * plotW;
      const y = padY + plotH - ((value - minMaxClamp(value, yMin, yMax) - yMin) / span) * plotH;
      return `${index === 0 ? 'M' : 'L'}${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(' ');
}

function minMaxClamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export function formatFolioCurrency(value: number, currency = 'USD'): string {
  return new Intl.NumberFormat(undefined, {
    style: 'currency',
    currency,
    maximumFractionDigits: value >= 1_000_000 ? 0 : 2,
  }).format(value);
}

export function formatSignedPercent(value: number): string {
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toFixed(2)}%`;
}

export function formatCompactCurrency(value: number, currency = 'USD'): string {
  if (value >= 1_000_000) {
    return `$${(value / 1_000_000).toFixed(1)}M`;
  }
  if (value >= 1_000) {
    return `$${(value / 1_000).toFixed(0)}K`;
  }
  return formatFolioCurrency(value, currency);
}
