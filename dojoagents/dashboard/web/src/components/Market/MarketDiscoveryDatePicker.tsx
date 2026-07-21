import { FolioDatePicker } from '../Folio/FolioDatePicker';
import { useTranslation } from '../../hooks/useTranslation';

interface MarketDiscoveryDatePickerProps {
  value: string;
  minDate: string;
  maxDate: string;
  disabled?: boolean;
  onChange: (value: string) => void;
}

export function MarketDiscoveryDatePicker({
  value,
  minDate,
  maxDate,
  disabled = false,
  onChange,
}: MarketDiscoveryDatePickerProps) {
  const { t } = useTranslation();

  if (!value || !minDate || !maxDate) return null;

  return (
    <FolioDatePicker
      className="mesh-sector-movers-bar__date"
      value={value}
      minDate={minDate}
      maxDate={maxDate}
      disabled={disabled}
      ariaLabel={t('marketPage.eventTimeHintBody')}
      title={t('marketPage.eventTimeHintBody')}
      onChange={onChange}
    />
  );
}
