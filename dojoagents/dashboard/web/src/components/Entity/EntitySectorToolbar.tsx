import type { SectorLevelKey } from '../../types/sector';
import type { SectorPathSelection, SectorTaxonomyDocument } from '../../types/sectorTaxonomy';
import { EntitySectorSelect } from './EntitySectorSelect';

interface EntitySectorToolbarProps {
  taxonomy: SectorTaxonomyDocument;
  selection: SectorPathSelection;
  classificationRole: 'primary' | 'secondary';
  onSelectionChange: (next: SectorPathSelection) => void;
  onOpenSphereLevel?: (level: SectorLevelKey) => void;
}

export function EntitySectorToolbar({
  taxonomy,
  selection,
  classificationRole,
  onSelectionChange,
  onOpenSphereLevel,
}: EntitySectorToolbarProps) {
  return (
    <div className={`core-sector-toolbar core-sector-toolbar--${classificationRole}`}>
      <EntitySectorSelect
        level="L1"
        taxonomy={taxonomy}
        selection={selection}
        onChange={onSelectionChange}
        onOpenSphereLevel={onOpenSphereLevel}
      />
      <EntitySectorSelect
        level="L2"
        taxonomy={taxonomy}
        selection={selection}
        onChange={onSelectionChange}
        onOpenSphereLevel={onOpenSphereLevel}
      />
      <EntitySectorSelect
        level="L3"
        taxonomy={taxonomy}
        selection={selection}
        onChange={onSelectionChange}
        onOpenSphereLevel={onOpenSphereLevel}
      />
    </div>
  );
}
