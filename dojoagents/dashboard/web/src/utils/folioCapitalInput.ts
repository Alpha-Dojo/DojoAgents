export type FolioCapitalEnUnit = 'M' | 'K';

export function capitalToDisplayValue(
  amount: number,
  locale: 'zh' | 'en',
  enUnit: FolioCapitalEnUnit = 'M',
): string {
  if (!Number.isFinite(amount) || amount < 0) return '0';
  let scaled: number;
  if (locale === 'zh') {
    scaled = amount / 10_000;
  } else if (enUnit === 'K') {
    scaled = amount / 1_000;
  } else {
    scaled = amount / 1_000_000;
  }
  if (Number.isInteger(scaled)) return String(scaled);
  return String(Number(scaled.toFixed(2)));
}

export function capitalFromDisplayValue(
  raw: string,
  locale: 'zh' | 'en',
  enUnit: FolioCapitalEnUnit = 'M',
): number {
  const parsed = Number(raw.replace(/,/g, ''));
  if (!Number.isFinite(parsed) || parsed < 0) return 0;
  if (locale === 'zh') return parsed * 10_000;
  if (enUnit === 'K') return parsed * 1_000;
  return parsed * 1_000_000;
}

export function toggleCapitalEnUnit(unit: FolioCapitalEnUnit): FolioCapitalEnUnit {
  return unit === 'M' ? 'K' : 'M';
}
