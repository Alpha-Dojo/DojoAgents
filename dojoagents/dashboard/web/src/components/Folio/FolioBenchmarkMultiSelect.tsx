import type { CSSProperties } from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from '../../hooks/useTranslation';
import type { MarketCode } from '../../types/market';
import { MARKET_FLAG } from '../../utils/marketDisplay';
import { formatPerformanceReturnPercent, PERFORMANCE_MARKET_CLASS } from '../../utils/sectorPerformanceSeries';

export type FolioBenchmarkMultiSelectOption = {
  kind: 'option';
  symbol: string;
  label: string;
  market: MarketCode;
};

export type FolioBenchmarkMultiSelectHeader = {
  kind: 'header';
  id: string;
  label: string;
};

export type FolioBenchmarkMultiSelectEntry =
  | FolioBenchmarkMultiSelectOption
  | FolioBenchmarkMultiSelectHeader;

interface FolioBenchmarkMultiSelectProps {
  'aria-label': string;
  className?: string;
  options: FolioBenchmarkMultiSelectEntry[];
  selected: string[];
  onToggle: (symbol: string) => void;
  /** Single-choice mode: replaces selection and closes the menu on pick. */
  singleSelect?: boolean;
  onSelect?: (symbol: string) => void;
  /** Rebased benchmark index (100 = flat); shown beside the trigger label when set. */
  returnValue?: number | null;
  /** Match folio-performance head chips instead of standalone dropdown styling. */
  variant?: 'default' | 'inline';
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
  singleSelect = false,
  onSelect,
  returnValue = null,
  variant = 'default',
}: FolioBenchmarkMultiSelectProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [dropdownStyle, setDropdownStyle] = useState<CSSProperties>({});
  const rootRef = useRef<HTMLDivElement>(null);
  const dropdownRef = useRef<HTMLUListElement>(null);

  const selectableOptions = useMemo(
    () => options.filter((entry): entry is FolioBenchmarkMultiSelectOption => entry.kind === 'option'),
    [options],
  );

  const selectedOptions = useMemo(
    () => selectableOptions.filter((option) => selected.includes(option.symbol)),
    [selectableOptions, selected],
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

  const handleOptionClick = useCallback(
    (symbol: string) => {
      if (singleSelect) {
        onSelect?.(symbol);
        setOpen(false);
        return;
      }
      onToggle(symbol);
    },
    [onSelect, onToggle, singleSelect],
  );

  const dropdown = open
    ? createPortal(
        <ul
          className="folio-benchmark-multi__dropdown dojo-dropdown-select__dropdown"
          role="listbox"
          aria-label={ariaLabel}
          aria-multiselectable={singleSelect ? 'false' : 'true'}
          ref={dropdownRef}
          style={dropdownStyle}
        >
          {options.map((entry) => {
            if (entry.kind === 'header') {
              return (
                <li key={entry.id} role="presentation" className="folio-benchmark-multi__group">
                  <span className="folio-benchmark-multi__group-label">{entry.label}</span>
                </li>
              );
            }
            const active = selected.includes(entry.symbol);
            return (
              <li key={entry.symbol} role="presentation">
                <button
                  type="button"
                  role="option"
                  aria-selected={active}
                  className={`folio-benchmark-multi__option dojo-dropdown-select__option${
                    active ? ' folio-benchmark-multi__option--active' : ''
                  }`}
                  onClick={() => handleOptionClick(entry.symbol)}
                >
                  <span className="folio-benchmark-multi__option-leading">
                    <span className="folio-benchmark-select__flag" aria-hidden>
                      {MARKET_FLAG[entry.market]}
                    </span>
                    <span className="dojo-dropdown-select__option-label">{entry.label}</span>
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
      <span
        className={
          variant === 'inline' ? 'folio-performance__inline-flag' : 'folio-benchmark-select__flag'
        }
        aria-hidden
      >
        {MARKET_FLAG[selectedOptions[0].market]}
      </span>
    ) : null;

  const inlineMarket =
    variant === 'inline' && selectedOptions.length === 1 ? selectedOptions[0].market : null;

  return (
    <div
      className={[
        'folio-benchmark-multi',
        open ? 'folio-benchmark-multi--open' : '',
        variant === 'inline' ? 'folio-benchmark-multi--inline' : '',
        className,
      ]
        .filter(Boolean)
        .join(' ')}
      ref={rootRef}
    >
      <button
        type="button"
        className={
          variant === 'inline'
            ? [
                'folio-benchmark-multi__trigger',
                'folio-performance__inline-benchmark',
                inlineMarket
                  ? `folio-performance__inline-market--${PERFORMANCE_MARKET_CLASS[inlineMarket]}`
                  : '',
                open ? 'folio-benchmark-multi__trigger--open' : '',
              ]
                .filter(Boolean)
                .join(' ')
            : `folio-benchmark-multi__trigger dojo-dropdown-select__trigger${
                open ? ' dojo-dropdown-select__trigger--open' : ''
              }`
        }
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={ariaLabel}
        onClick={() => setOpen((prev) => !prev)}
      >
        {variant === 'inline' ? (
          <>
            {triggerPrefix}
            <span className="folio-performance__inline-benchmark-label">{triggerLabel}</span>
            {returnValue != null ? (
              <span
                className={`folio-performance__inline-return folio-performance__inline-return--${
                  returnValue >= 100 ? 'up' : 'down'
                }`}
              >
                {formatPerformanceReturnPercent(returnValue)}
              </span>
            ) : null}
            <ChevronIcon />
          </>
        ) : (
          <>
            <span className="dojo-dropdown-select__value">
              {triggerPrefix}
              <span className="dojo-dropdown-select__value-label">{triggerLabel}</span>
              {singleSelect && returnValue != null ? (
                <span
                  className={`folio-benchmark-multi__trigger-return folio-benchmark-multi__trigger-return--${
                    returnValue >= 100 ? 'up' : 'down'
                  }`}
                >
                  {formatPerformanceReturnPercent(returnValue)}
                </span>
              ) : null}
            </span>
            <ChevronIcon />
          </>
        )}
      </button>
      {dropdown}
    </div>
  );
}
