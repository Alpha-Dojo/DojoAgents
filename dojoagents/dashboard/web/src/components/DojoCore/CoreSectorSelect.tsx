import { useMemo } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import type { SectorLevelKey } from '../../types/dojoSphere';
import type { SectorPathSelection, SectorTaxonomyDocument } from '../../types/sectorTaxonomy';
import {
  listLevel1Options,
  listLevel2Options,
  listLevel3Options,
} from '../../utils/sectorTaxonomy';

interface CoreSectorSelectProps {
  level: SectorLevelKey;
  taxonomy: SectorTaxonomyDocument;
  selection: SectorPathSelection;
  onChange: (next: SectorPathSelection) => void;
  onOpenSphereLevel?: (level: SectorLevelKey) => void;
}

export function CoreSectorSelect({
  level,
  taxonomy,
  selection,
  onChange,
  onOpenSphereLevel,
}: CoreSectorSelectProps) {
  const { locale, t } = useTranslation();

  const options = useMemo(() => {
    if (level === 'L1') return listLevel1Options(taxonomy);
    if (level === 'L2') return listLevel2Options(taxonomy, selection.level1Id);
    return listLevel3Options(taxonomy, selection.level1Id, selection.level2Id);
  }, [level, taxonomy, selection.level1Id, selection.level2Id]);

  const value =
    level === 'L1'
      ? selection.level1Id
      : level === 'L2'
        ? selection.level2Id
        : selection.level3Id;

  const labelFor = (zh: string, en: string) => (locale === 'zh' ? zh || en : en || zh);

  const levelLabelKey =
    level === 'L1' ? 'sphere.level1' : level === 'L2' ? 'sphere.level2' : 'sphere.level3';

  const handleChange = (nextValue: string) => {
    if (level === 'L1') {
      const l2 = listLevel2Options(taxonomy, nextValue)[0];
      const l3 = l2 ? listLevel3Options(taxonomy, nextValue, l2.id)[0] : undefined;
      onChange({
        level1Id: nextValue,
        level2Id: l2?.id ?? '',
        level3Id: l3?.id ?? '',
      });
      return;
    }
    if (level === 'L2') {
      const l3 = listLevel3Options(taxonomy, selection.level1Id, nextValue)[0];
      onChange({
        level1Id: selection.level1Id,
        level2Id: nextValue,
        level3Id: l3?.id ?? '',
      });
      return;
    }
    onChange({
      level1Id: selection.level1Id,
      level2Id: selection.level2Id,
      level3Id: nextValue,
    });
  };

  return (
    <div className="core-sector-field">
      <button
        type="button"
        className="core-sector-field__badge"
        disabled={!onOpenSphereLevel}
        aria-label={t('core.openLevelInSphere', { level })}
        title={t('core.openLevelInSphere', { level })}
        onClick={() => onOpenSphereLevel?.(level)}
      >
        {level}
      </button>
      <select
        className="core-sector-field__control"
        value={value}
        aria-label={t(levelLabelKey)}
        onChange={(event) => handleChange(event.target.value)}
      >
        {options.map((item) => (
          <option key={item.id} value={item.id}>
            {labelFor(item.name.zh, item.name.en)}
          </option>
        ))}
      </select>
    </div>
  );
}
