import { useEffect, useRef, useState } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import type { FolioAllocationStrategy } from '../../types/dojoFolio';

const STRATEGY_NAME_KEYS: Record<FolioAllocationStrategy, string> = {
  market_cap: 'folio.allocateStrategyNameMarketCap',
  equal_weight: 'folio.allocateStrategyNameEqualWeight',
  risk_parity: 'folio.allocateStrategyNameRiskParity',
};

const STRATEGY_DESC_KEYS: Record<FolioAllocationStrategy, string> = {
  market_cap: 'folio.allocateStrategyDescMarketCap',
  equal_weight: 'folio.allocateStrategyDescEqualWeight',
  risk_parity: 'folio.allocateStrategyDescRiskParity',
};

interface FolioAllocateMenuProps {
  disabled?: boolean;
  onAllocate: (strategy: FolioAllocationStrategy) => void;
}

function ChevronIcon() {
  return (
    <svg className="folio-allocate-menu__chevron" viewBox="0 0 24 24" width="10" height="10" aria-hidden>
      <path
        d="M6 9l6 6 6-6"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function FolioAllocateMenu({ disabled = false, onAllocate }: FolioAllocateMenuProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handlePointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    window.addEventListener('mousedown', handlePointerDown);
    return () => window.removeEventListener('mousedown', handlePointerDown);
  }, [open]);

  const strategyName = (strategy: FolioAllocationStrategy) => t(STRATEGY_NAME_KEYS[strategy]);
  const strategyDesc = (strategy: FolioAllocationStrategy) => t(STRATEGY_DESC_KEYS[strategy]);

  return (
    <div className="folio-allocate-menu" ref={rootRef}>
      <button
        type="button"
        className={`folio-allocate-menu__trigger ${open ? 'folio-allocate-menu__trigger--open' : ''}`}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={t('folio.autoAllocate')}
        disabled={disabled}
        onClick={() => setOpen((prev) => !prev)}
      >
        <span>{t('folio.autoAllocate')}</span>
        <ChevronIcon />
      </button>
      {open ? (
        <ul
          className="folio-allocate-menu__dropdown"
          role="listbox"
          aria-label={t('folio.allocateStrategyLabel')}
        >
          {(['market_cap', 'equal_weight', 'risk_parity'] as FolioAllocationStrategy[]).map((strategy) => (
            <li key={strategy} role="presentation">
              <button
                type="button"
                role="option"
                className="folio-allocate-menu__option"
                onClick={() => {
                  setOpen(false);
                  onAllocate(strategy);
                }}
              >
                <span className="folio-allocate-menu__option-line">
                  <span className="folio-allocate-menu__option-name">{strategyName(strategy)}</span>
                  <span className="folio-allocate-menu__option-sep">：</span>
                  <span className="folio-allocate-menu__option-desc">{strategyDesc(strategy)}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
