import { useMemo } from 'react';
import {
  clampStartDate,
  computeStartDateBounds,
} from '../../utils/folioStartDate';

interface FolioHoldingOpenDatePickerProps {
  value: string;
  earliestDataDate?: string | null;
  usesDefault?: boolean;
  onChange: (value: string) => void;
}

export function FolioHoldingOpenDatePicker({
  value,
  earliestDataDate,
  usesDefault = false,
  onChange,
}: FolioHoldingOpenDatePickerProps) {
  const bounds = useMemo(
    () => computeStartDateBounds(earliestDataDate),
    [earliestDataDate],
  );
  const selected = clampStartDate(value, bounds.min, bounds.max);

  return (
    <input
      type="date"
      className={`folio-table__date-input${usesDefault ? ' folio-table__date-input--default' : ''}`}
      value={selected}
      min={bounds.min}
      max={bounds.max}
      title={usesDefault ? selected : undefined}
      onChange={(event) => onChange(event.target.value)}
    />
  );
}
