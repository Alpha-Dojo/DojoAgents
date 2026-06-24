import { useEffect, useMemo } from 'react';
import { clampStartDate, computeStartDateBounds } from '../../utils/folioStartDate';

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
    <input
      type="date"
      className="folio-config__input folio-config__date"
      value={selected}
      min={bounds.min}
      max={bounds.max}
      onChange={(event) => onChange(event.target.value)}
    />
  );
}
