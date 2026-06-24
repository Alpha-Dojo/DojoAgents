import type { SectorLevelKey } from '../../types/dojoSphere';
import type { SectorPathSelection, SectorTaxonomyDocument } from '../../types/sectorTaxonomy';
import { CoreSectorSelect } from './CoreSectorSelect';

interface CoreSectorToolbarProps {
  taxonomy: SectorTaxonomyDocument;
  selection: SectorPathSelection;
  classificationRole: 'primary' | 'secondary';
  onSelectionChange: (next: SectorPathSelection) => void;
  onOpenSphereLevel?: (level: SectorLevelKey) => void;
}

export function CoreSectorToolbar({
  taxonomy,
  selection,
  classificationRole,
  onSelectionChange,
  onOpenSphereLevel,
}: CoreSectorToolbarProps) {
  return (
    <div className={`core-sector-toolbar core-sector-toolbar--${classificationRole}`}>
      <CoreSectorSelect
        level="L1"
        taxonomy={taxonomy}
        selection={selection}
        onChange={onSelectionChange}
        onOpenSphereLevel={onOpenSphereLevel}
      />
      <CoreSectorSelect
        level="L2"
        taxonomy={taxonomy}
        selection={selection}
        onChange={onSelectionChange}
        onOpenSphereLevel={onOpenSphereLevel}
      />
      <CoreSectorSelect
        level="L3"
        taxonomy={taxonomy}
        selection={selection}
        onChange={onSelectionChange}
        onOpenSphereLevel={onOpenSphereLevel}
      />
    </div>
  );
}
