import { useEffect, useMemo } from 'react';
import { clampStartDate, computeStartDateBounds } from '../../utils/folioStartDate';
import { FolioDatePicker } from './FolioDatePicker';

interface FolioStartDatePickerProps {
  value: string;
  onChange: (value: string) => void;
}

export function FolioStartDatePicker({ value, onChange }: FolioStartDatePickerProps) {
  const bounds = useMemo(() => computeStartDateBounds(), []);

  const selected = clampStartDate(value, bounds.min, bounds.max);

  useEffect(() => {
    if (selected !== value) {
      onChange(selected);
    }
  }, [onChange, selected, value]);

  return (
    <FolioDatePicker
      className="folio-config__input folio-config__date"
      value={selected}
      minDate={bounds.min}
      maxDate={bounds.max}
      onChange={onChange}
    />
  );
}
