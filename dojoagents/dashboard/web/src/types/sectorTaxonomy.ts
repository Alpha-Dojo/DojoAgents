export interface BilingualLabel {
  zh: string;
  en: string;
}

export interface SectorTaxonomyL3 {
  id: string;
  name: BilingualLabel;
  definition?: BilingualLabel;
}

export interface SectorTaxonomyL2 {
  id: string;
  name: BilingualLabel;
  description?: BilingualLabel;
  level_3: SectorTaxonomyL3[];
}

export interface SectorTaxonomyL1 {
  id: string;
  name: BilingualLabel;
  description?: BilingualLabel;
  level_2: SectorTaxonomyL2[];
}

export interface SectorTaxonomyDocument {
  version: string;
  id_scheme: string;
  level_1: SectorTaxonomyL1[];
}

export interface SectorPathSelection {
  level1Id: string;
  level2Id: string;
  level3Id: string;
}

export interface ResolvedSectorPath {
  level1: SectorTaxonomyL1;
  level2: SectorTaxonomyL2;
  level3: SectorTaxonomyL3;
}
