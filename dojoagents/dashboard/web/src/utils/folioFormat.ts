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

const FOLIO_CURRENCY_PREFIX: Record<string, string> = {
  USD: 'US$',
  CNY: '¥',
  HKD: 'HK$',
};

export function formatFolioCurrency(value: number, currency = 'USD'): string {
  return new Intl.NumberFormat(undefined, {
    style: 'currency',
    currency,
    maximumFractionDigits: value >= 1_000_000 ? 0 : 2,
  }).format(value);
}

/** Compact currency for tight UI (e.g. sector allocation donuts): US$19.18M, ¥17.76M, 850K. */
export function formatFolioCompactCurrency(value: number, currency = 'USD'): string {
  if (!Number.isFinite(value) || value <= 0) return '—';
  const prefix = FOLIO_CURRENCY_PREFIX[currency] ?? `${currency} `;
  const abs = Math.abs(value);
  if (abs >= 1_000_000_000) {
    return `${prefix}${(value / 1_000_000_000).toFixed(2)}B`;
  }
  if (abs >= 1_000_000) {
    return `${prefix}${(value / 1_000_000).toFixed(2)}M`;
  }
  if (abs >= 1_000) {
    return `${prefix}${Math.round(value / 1_000)}K`;
  }
  return `${prefix}${Math.round(value)}`;
}

export function formatSignedPercent(value: number): string {
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toFixed(2)}%`;
}

export function formatCompactAmount(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return '—';
  const abs = Math.abs(value);
  if (abs >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(2)}B`;
  if (abs >= 1_000_000) return `${(value / 1_000_000).toFixed(3)}M`;
  if (abs >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return String(Math.round(value));
}

export function formatCompactCurrency(value: number, currency = 'USD'): string {
  return formatFolioCompactCurrency(value, currency);
}
