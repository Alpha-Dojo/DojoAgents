import { useEffect, useRef, useState } from 'react';
import { useAgentModel } from '../agent/AgentModelContext';
import { useTranslation } from '../hooks/useTranslation';
import './AgentModelSwitcher.css';

function SparkIcon() {
  return (
    <svg
      className="model-menu__icon"
      viewBox="0 0 24 24"
      width="14"
      height="14"
      aria-hidden
    >
      <path
        d="M12 2l1.4 4.6L18 8l-4.6 1.4L12 14l-1.4-4.6L6 8l4.6-1.4L12 2zM18 14l.8 2.6L21.5 17l-2.7.8L18 20.5l-.8-2.7L14.5 17l2.7-.8L18 14z"
        fill="currentColor"
      />
    </svg>
  );
}

function ChevronIcon() {
  return (
    <svg
      className="model-menu__chevron"
      viewBox="0 0 24 24"
      width="12"
      height="12"
      aria-hidden
    >
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

export function AgentModelSwitcher({ variant = 'composer' }: { variant?: 'composer' | 'header' }) {
  const { t } = useTranslation();
  const { models, selectedModel, selectedModelId, loading, setSelectedModelId } = useAgentModel();
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

  const label = loading
    ? t('agentModel.loading')
    : (selectedModel?.label ?? t('agentModel.label'));

  return (
    <div className={`model-menu model-menu--${variant}`} ref={rootRef}>
      <button
        type="button"
        className={`model-menu__trigger ${open ? 'model-menu__trigger--open' : ''}`}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={t('agentModel.label')}
        disabled={loading}
        onClick={() => setOpen((prev) => !prev)}
      >
        <SparkIcon />
        <span className="model-menu__value">{label}</span>
        <ChevronIcon />
      </button>
      {open && (
        <ul className="model-menu__dropdown" role="listbox" aria-label={t('agentModel.label')}>
          {models.map((model) => {
            const disabled = !model.available;
            return (
              <li key={model.id} role="presentation">
                <button
                  type="button"
                  role="option"
                  aria-selected={selectedModelId === model.id}
                  aria-disabled={disabled}
                  disabled={disabled}
                  title={disabled ? t('agentModel.comingSoon') : undefined}
                  className={[
                    'model-menu__option',
                    selectedModelId === model.id ? 'model-menu__option--active' : '',
                    disabled ? 'model-menu__option--disabled' : '',
                  ]
                    .filter(Boolean)
                    .join(' ')}
                  onClick={() => {
                    if (disabled) return;
                    setSelectedModelId(model.id);
                    setOpen(false);
                  }}
                >
                  <span className="model-menu__option-label">{model.label}</span>
                  {disabled && (
                    <span className="model-menu__option-badge">{t('agentModel.comingSoon')}</span>
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
