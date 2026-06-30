import { useTranslation } from '../../hooks/useTranslation';
import type { FolioNavWindowPreset } from '../../utils/folioNavWindow';
import { DojoDropdownSelect } from '../ui/DojoDropdownSelect';

const PRESETS: FolioNavWindowPreset[] = ['3m', '6m', '1y', 'all'];

const PRESET_LABEL_KEY: Record<
  FolioNavWindowPreset,
  'folio.navWindow3m' | 'folio.navWindow6m' | 'folio.navWindow1y' | 'folio.navWindowAll'
> = {
  '3m': 'folio.navWindow3m',
  '6m': 'folio.navWindow6m',
  '1y': 'folio.navWindow1y',
  all: 'folio.navWindowAll',
};

interface FolioNavWindowPresetsProps {
  value: FolioNavWindowPreset;
  onChange: (preset: FolioNavWindowPreset) => void;
}

export function FolioNavWindowPresets({ value, onChange }: FolioNavWindowPresetsProps) {
  const { t } = useTranslation();
  const ariaLabel = t('folio.navWindowLabel');
  const options = PRESETS.map((preset) => ({
    value: preset,
    label: t(PRESET_LABEL_KEY[preset]),
  }));

  return (
    <div className="folio-performance__window-select-wrap">
      <DojoDropdownSelect
        aria-label={ariaLabel}
        className="folio-performance__window-select"
        options={options}
        value={value}
        onChange={(nextValue) => onChange(nextValue as FolioNavWindowPreset)}
      />
    </div>
  );
}
