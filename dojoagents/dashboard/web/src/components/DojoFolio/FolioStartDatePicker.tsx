import { useEffect, useMemo } from 'react';
import { clampStartDate, computeStartDateBounds } from '../../utils/folioStartDate';

interface FolioStartDatePickerProps {
  value: string;
  earliestDataDate?: string | null;
  onChange: (value: string) => void;
}

export function FolioStartDatePicker({
  value,
  earliestDataDate,
  onChange,
}: FolioStartDatePickerProps) {
  const bounds = useMemo(
    () => computeStartDateBounds(earliestDataDate),
    [earliestDataDate],
  );

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
