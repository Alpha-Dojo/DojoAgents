import type { CSSProperties } from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from '../../hooks/useTranslation';
import type { MarketCode } from '../../types/market';
import { MARKET_FLAG } from '../../utils/marketDisplay';

export interface FolioBenchmarkMultiSelectOption {
  symbol: string;
  label: string;
  market: MarketCode;
}

interface FolioBenchmarkMultiSelectProps {
  'aria-label': string;
  className?: string;
  options: FolioBenchmarkMultiSelectOption[];
  selected: string[];
  onToggle: (symbol: string) => void;
}

function ChevronIcon() {
  return (
    <svg
      className="folio-benchmark-multi__chevron"
      viewBox="0 0 24 24"
      width="12"
      height="12"
      aria-hidden
    >
      <path
        d="M6 9l6 6 6-6"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.75"
      />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg
      className="folio-benchmark-multi__check"
      viewBox="0 0 12 12"
      width="11"
      height="11"
      aria-hidden
    >
      <path
        d="M2.5 6.1 5 8.6 9.5 3.9"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.4"
      />
    </svg>
  );
}

export function FolioBenchmarkMultiSelect({
  'aria-label': ariaLabel,
  className = '',
  options,
  selected,
  onToggle,
}: FolioBenchmarkMultiSelectProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [dropdownStyle, setDropdownStyle] = useState<CSSProperties>({});
  const rootRef = useRef<HTMLDivElement>(null);
  const dropdownRef = useRef<HTMLUListElement>(null);

  const selectedOptions = useMemo(
    () => options.filter((option) => selected.includes(option.symbol)),
    [options, selected],
  );

  const triggerLabel = useMemo(() => {
    if (selectedOptions.length === 0) return t('sectorPage.benchmarkNone');
    if (selectedOptions.length === 1) return selectedOptions[0].label;
    return t('folio.benchmarkSelectedCount', { count: selectedOptions.length });
  }, [selectedOptions, t]);

  const updateDropdownPosition = useCallback(() => {
    const rect = rootRef.current?.getBoundingClientRect();
    const dropdown = dropdownRef.current;
    if (!rect) return;

    const boundaryEl =
      rootRef.current?.closest('.folio-view') ??
      rootRef.current?.closest('.app-main__content');
    const boundary = boundaryEl?.getBoundingClientRect();
    const pad = 6;
    const maxRight = (boundary?.right ?? window.innerWidth) - pad;
    const minLeft = (boundary?.left ?? 0) + pad;
    const availableWidth = Math.max(maxRight - minLeft, 120);

    const dropdownWidth = dropdown?.getBoundingClientRect().width ?? rect.width;
    const width = Math.min(dropdownWidth, availableWidth);

    let left = rect.right - width;
    if (left + width > maxRight) {
      left = maxRight - width;
    }
    if (left < minLeft) {
      left = minLeft;
    }

    setDropdownStyle({
      left,
      top: rect.bottom + 4,
      width: 'max-content',
      maxWidth: availableWidth,
    });
  }, []);

  useEffect(() => {
    if (!open) return;

    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (
        !rootRef.current?.contains(target) &&
        !dropdownRef.current?.contains(target)
      ) {
        setOpen(false);
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    const handleViewportChange = () => updateDropdownPosition();

    updateDropdownPosition();
    const frame = requestAnimationFrame(() => updateDropdownPosition());
    window.addEventListener('mousedown', handlePointerDown);
    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('resize', handleViewportChange);
    window.addEventListener('scroll', handleViewportChange, true);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener('mousedown', handlePointerDown);
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('resize', handleViewportChange);
      window.removeEventListener('scroll', handleViewportChange, true);
    };
  }, [open, updateDropdownPosition]);

  const dropdown = open
    ? createPortal(
        <ul
          className="folio-benchmark-multi__dropdown dojo-dropdown-select__dropdown"
          role="listbox"
          aria-label={ariaLabel}
          aria-multiselectable="true"
          ref={dropdownRef}
          style={dropdownStyle}
        >
          {options.map((option) => {
            const active = selected.includes(option.symbol);
            return (
              <li key={option.symbol} role="presentation">
                <button
                  type="button"
                  role="option"
                  aria-selected={active}
                  className={`folio-benchmark-multi__option dojo-dropdown-select__option${
                    active ? ' folio-benchmark-multi__option--active' : ''
                  }`}
                  onClick={() => onToggle(option.symbol)}
                >
                  <span className="folio-benchmark-multi__option-leading">
                    <span className="folio-benchmark-select__flag" aria-hidden>
                      {MARKET_FLAG[option.market]}
                    </span>
                    <span className="dojo-dropdown-select__option-label">{option.label}</span>
                  </span>
                  <span
                    className={`folio-benchmark-multi__check-slot${
                      active ? ' folio-benchmark-multi__check-slot--active' : ''
                    }`}
                    aria-hidden
                  >
                    {active ? <CheckIcon /> : null}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>,
        document.body,
      )
    : null;

  const triggerPrefix =
    selectedOptions.length === 1 ? (
      <span className="folio-benchmark-select__flag" aria-hidden>
        {MARKET_FLAG[selectedOptions[0].market]}
      </span>
    ) : null;

  return (
    <div
      className={['folio-benchmark-multi', open ? 'folio-benchmark-multi--open' : '', className]
        .filter(Boolean)
        .join(' ')}
      ref={rootRef}
    >
      <button
        type="button"
        className={`folio-benchmark-multi__trigger dojo-dropdown-select__trigger${
          open ? ' dojo-dropdown-select__trigger--open' : ''
        }`}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={ariaLabel}
        onClick={() => setOpen((prev) => !prev)}
      >
        <span className="dojo-dropdown-select__value">
          {triggerPrefix}
          <span className="dojo-dropdown-select__value-label">{triggerLabel}</span>
        </span>
        <ChevronIcon />
      </button>
      {dropdown}
    </div>
  );
}
