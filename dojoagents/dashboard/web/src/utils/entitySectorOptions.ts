import type { EntitySectorLabelPath, EntitySectorOption } from '../types/entity';
import type { SectorPathSelection } from '../types/sectorTaxonomy';

export function selectionFromSectorOption(option: EntitySectorOption): SectorPathSelection {
  return {
    level1Id: option.level1Id,
    level2Id: option.level2Id,
    level3Id: option.level3Id,
  };
}

export function selectionKey(selection: SectorPathSelection): string {
  return `${selection.level1Id}:${selection.level2Id}:${selection.level3Id}`;
}

export function findSectorOptionIndex(
  options: EntitySectorOption[],
  selection: SectorPathSelection | null,
): number {
  if (!selection) return -1;
  const key = selectionKey(selection);
  return options.findIndex((option) => selectionKey(selectionFromSectorOption(option)) === key);
}

export function activeClassificationRole(
  options: EntitySectorOption[],
  selection: SectorPathSelection | null,
): 'primary' | 'secondary' {
  const index = findSectorOptionIndex(options, selection);
  if (index >= 0) return options[index].role;
  return 'primary';
}

export function formatSectorOptionL3(
  option: EntitySectorOption,
  text: (value: EntitySectorLabelPath['level3']) => string,
): string {
  return text(option.label.level3);
}
