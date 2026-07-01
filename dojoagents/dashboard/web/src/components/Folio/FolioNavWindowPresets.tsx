import { useTranslation } from '../../hooks/useTranslation';
import type { FolioNavWindowPreset } from '../../utils/folioNavWindow';

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

  return (
    <label className="folio-performance__window-select-wrap">
      <span className="sr-only">{t('folio.navWindowLabel')}</span>
      <select
        className="folio-performance__window-select folio-config__select"
        value={value}
        aria-label={t('folio.navWindowLabel')}
        onChange={(event) => onChange(event.target.value as FolioNavWindowPreset)}
      >
        {PRESETS.map((preset) => (
          <option key={preset} value={preset}>
            {t(PRESET_LABEL_KEY[preset])}
          </option>
        ))}
      </select>
    </label>
  );
}
