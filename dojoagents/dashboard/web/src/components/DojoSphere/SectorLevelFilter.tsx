import { useMemo } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import type { SectorTaxonomyDocument } from '../../types/sectorTaxonomy';
import {
  listLevel1Options,
  listLevel2Options,
  listLevel3Options,
} from '../../utils/sectorTaxonomy';
import { DojoDropdownSelect } from '../ui';
import './SectorLevelFilter.css';

interface SectorLevelFilterProps {
  taxonomy: SectorTaxonomyDocument;
  level1Id: string;
  level2Id: string;
  level3Id: string;
  onChange: (next: { level1Id: string; level2Id: string; level3Id: string }) => void;
}

export function SectorLevelFilter({
  taxonomy,
  level1Id,
  level2Id,
  level3Id,
  onChange,
}: SectorLevelFilterProps) {
  const { locale, t } = useTranslation();

  const level1Options = useMemo(() => listLevel1Options(taxonomy), [taxonomy]);
  const level2Options = useMemo(
    () => listLevel2Options(taxonomy, level1Id),
    [taxonomy, level1Id],
  );
  const level3Options = useMemo(
    () => listLevel3Options(taxonomy, level1Id, level2Id),
    [taxonomy, level1Id, level2Id],
  );

  const labelFor = (zh: string, en: string) => (locale === 'zh' ? zh || en : en || zh);

  return (
    <div className="sphere-level-filter" role="group" aria-label={t('sphere.filterLabel')}>
      <div className="sphere-level-filter__field">
        <span className="sphere-level-filter__label">{t('sphere.level1')}</span>
        <DojoDropdownSelect
          aria-label={t('sphere.level1')}
          className="sphere-level-filter__select"
          value={level1Id}
          onChange={(nextL1) => {
            const l2 = listLevel2Options(taxonomy, nextL1)[0];
            const l3 = l2 ? listLevel3Options(taxonomy, nextL1, l2.id)[0] : undefined;
            onChange({
              level1Id: nextL1,
              level2Id: l2?.id ?? '',
              level3Id: l3?.id ?? '',
            });
          }}
          options={level1Options.map((item) => ({
            value: item.id,
            label: labelFor(item.name.zh, item.name.en),
          }))}
        />
      </div>

      <div className="sphere-level-filter__field">
        <span className="sphere-level-filter__label">{t('sphere.level2')}</span>
        <DojoDropdownSelect
          aria-label={t('sphere.level2')}
          className="sphere-level-filter__select"
          value={level2Id}
          onChange={(nextL2) => {
            const l3 = listLevel3Options(taxonomy, level1Id, nextL2)[0];
            onChange({
              level1Id,
              level2Id: nextL2,
              level3Id: l3?.id ?? '',
            });
          }}
          options={level2Options.map((item) => ({
            value: item.id,
            label: labelFor(item.name.zh, item.name.en),
          }))}
        />
      </div>

      <div className="sphere-level-filter__field">
        <span className="sphere-level-filter__label">{t('sphere.level3')}</span>
        <DojoDropdownSelect
          aria-label={t('sphere.level3')}
          className="sphere-level-filter__select"
          value={level3Id}
          onChange={(level3Id) => onChange({ level1Id, level2Id, level3Id })}
          options={level3Options.map((item) => ({
            value: item.id,
            label: labelFor(item.name.zh, item.name.en),
          }))}
        />
      </div>
    </div>
  );
}
