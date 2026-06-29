import type { SectorLevelKey } from '../types/sector';
import type { ResolvedSectorPath } from '../types/sectorTaxonomy';

export function scopeSectorName(
  path: ResolvedSectorPath,
  scope: SectorLevelKey,
  locale: 'zh' | 'en',
): string {
  if (scope === 'L1') {
    return locale === 'zh'
      ? path.level1.name.zh || path.level1.name.en
      : path.level1.name.en || path.level1.name.zh;
  }
  if (scope === 'L2') {
    return locale === 'zh'
      ? path.level2.name.zh || path.level2.name.en
      : path.level2.name.en || path.level2.name.zh;
  }
  return locale === 'zh'
    ? path.level3.name.zh || path.level3.name.en
    : path.level3.name.en || path.level3.name.zh;
}

export function scopeChartTitle(
  path: ResolvedSectorPath,
  scope: SectorLevelKey,
  locale: 'zh' | 'en',
): string {
  return `${scope} ${scopeSectorName(path, scope, locale)}`;
}
