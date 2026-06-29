import { useMemo } from 'react';
import {
  clampStartDate,
  computeStartDateBounds,
} from '../../utils/folioStartDate';
import { FolioDatePicker } from './FolioDatePicker';

interface FolioHoldingOpenDatePickerProps {
  value: string;
  /** Earliest allowed open date — typically the portfolio start date. */
  floorDate?: string | null;
  usesDefault?: boolean;
  disabled?: boolean;
  onChange: (value: string) => void;
}

export function FolioHoldingOpenDatePicker({
  value,
  floorDate,
  usesDefault = false,
  disabled = false,
  onChange,
}: FolioHoldingOpenDatePickerProps) {
  const bounds = useMemo(() => computeStartDateBounds(floorDate), [floorDate]);
  const selected = clampStartDate(value, bounds.min, bounds.max);

  return (
    <FolioDatePicker
      className={`folio-table__date-input${usesDefault ? ' folio-table__date-input--default' : ''}`}
      value={selected}
      minDate={bounds.min}
      maxDate={bounds.max}
      disabled={disabled}
      title={usesDefault ? selected : undefined}
      onChange={onChange}
    />
  );
}
