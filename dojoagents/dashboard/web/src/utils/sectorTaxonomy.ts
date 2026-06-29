import type {
  ResolvedSectorPath,
  SectorPathSelection,
  SectorTaxonomyDocument,
  SectorTaxonomyL1,
  SectorTaxonomyL2,
  SectorTaxonomyL3,
} from '../types/sectorTaxonomy';

export function slugifySectorLabel(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '') || 'unknown';
}

export function* iterSectorPaths(
  taxonomy: SectorTaxonomyDocument,
): Generator<ResolvedSectorPath> {
  for (const level1 of taxonomy.level_1) {
    for (const level2 of level1.level_2) {
      for (const level3 of level2.level_3) {
        yield { level1, level2, level3 };
      }
    }
  }
}

export function findSectorPathByIds(
  taxonomy: SectorTaxonomyDocument,
  selection: SectorPathSelection,
): ResolvedSectorPath | null {
  const level1 = taxonomy.level_1.find((item) => item.id === selection.level1Id);
  if (!level1) return null;
  const level2 = level1.level_2.find((item) => item.id === selection.level2Id);
  if (!level2) return null;
  const level3 = level2.level_3.find((item) => item.id === selection.level3Id);
  if (!level3) return null;
  return { level1, level2, level3 };
}

export function findSectorPathByLinkKey(
  taxonomy: SectorTaxonomyDocument,
  linkKey: string,
): ResolvedSectorPath | null {
  const needle = linkKey.trim().toLowerCase();
  const idSuffix = `.${needle.replace(/-/g, '_')}`;

  for (const path of iterSectorPaths(taxonomy)) {
    const l3Id = path.level3.id.toLowerCase();
    if (l3Id.endsWith(idSuffix) || l3Id.endsWith(`_${needle.replace(/-/g, '_')}`)) {
      return path;
    }
    if (slugifySectorLabel(path.level3.name.en) === needle) {
      return path;
    }
    if (slugifySectorLabel(path.level3.name.zh) === needle) {
      return path;
    }
  }
  return null;
}

export function findSectorPathByL3Name(
  taxonomy: SectorTaxonomyDocument,
  nameZh: string,
  nameEn: string,
): ResolvedSectorPath | null {
  const zh = nameZh.trim();
  const en = nameEn.trim();
  for (const path of iterSectorPaths(taxonomy)) {
    const pathZh = path.level3.name.zh.trim();
    const pathEn = path.level3.name.en.trim();
    if ((zh && pathZh === zh) || (en && pathEn === en)) {
      return path;
    }
  }
  return null;
}

export function findSectorPathByLevelName(
  taxonomy: SectorTaxonomyDocument,
  level: 'L1' | 'L2' | 'L3',
  name: string,
): ResolvedSectorPath | null {
  const needle = name.trim();
  if (!needle) return null;

  for (const path of iterSectorPaths(taxonomy)) {
    const node =
      level === 'L1' ? path.level1.name : level === 'L2' ? path.level2.name : path.level3.name;
    const zh = node.zh.trim();
    const en = node.en.trim();
    if ((zh && zh === needle) || (en && en === needle)) {
      return path;
    }
  }
  return null;
}

export function resolveSectorPathFromJump(
  taxonomy: SectorTaxonomyDocument,
  linkKey?: string | null,
  nameZh?: string,
  nameEn?: string,
): ResolvedSectorPath | null {
  const fromLink = linkKey ? findSectorPathByLinkKey(taxonomy, linkKey) : null;
  if (fromLink) return fromLink;
  if (nameZh || nameEn) {
    return findSectorPathByL3Name(taxonomy, nameZh ?? '', nameEn ?? '');
  }
  return null;
}

export function selectionFromPath(path: ResolvedSectorPath): SectorPathSelection {
  return {
    level1Id: path.level1.id,
    level2Id: path.level2.id,
    level3Id: path.level3.id,
  };
}

export function getDefaultSelection(taxonomy: SectorTaxonomyDocument): SectorPathSelection {
  const smartHome = findSectorPathByLinkKey(taxonomy, 'smart-home');
  if (smartHome) return selectionFromPath(smartHome);
  const first = iterSectorPaths(taxonomy).next().value;
  if (!first) {
    return { level1Id: '', level2Id: '', level3Id: '' };
  }
  return selectionFromPath(first);
}

/** DojoSphere landing sector: 科技 > 半导体与集成电路 > 芯片设计 */
export function getSectorDefaultSelection(taxonomy: SectorTaxonomyDocument): SectorPathSelection {
  const chipDesign =
    findSectorPathByLinkKey(taxonomy, 'chip-design') ??
    findSectorPathByL3Name(taxonomy, '芯片设计', 'Chip Design');
  if (chipDesign) return selectionFromPath(chipDesign);
  return getDefaultSelection(taxonomy);
}

export function listLevel2Options(
  taxonomy: SectorTaxonomyDocument,
  level1Id: string,
): SectorTaxonomyL2[] {
  return taxonomy.level_1.find((item) => item.id === level1Id)?.level_2 ?? [];
}

export function listLevel3Options(
  taxonomy: SectorTaxonomyDocument,
  level1Id: string,
  level2Id: string,
): SectorTaxonomyL3[] {
  return listLevel2Options(taxonomy, level1Id).find((item) => item.id === level2Id)?.level_3 ?? [];
}

export function listLevel1Options(taxonomy: SectorTaxonomyDocument): SectorTaxonomyL1[] {
  return taxonomy.level_1;
}
