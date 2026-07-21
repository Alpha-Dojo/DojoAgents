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

interface AgentModelSwitcherProps {
  variant?: 'composer' | 'header';
  onConfigureModel?: () => void;
}

export function AgentModelSwitcher({
  variant = 'composer',
  onConfigureModel,
}: AgentModelSwitcherProps) {
  const { t } = useTranslation();
  const {
    models,
    selectedModel,
    selectedModelId,
    agentReady,
    loading,
    saving,
    setSelectedModelId,
  } = useAgentModel();
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

  const disabled = loading || saving;
  const needsConfiguration =
    !loading && (!agentReady || !models.some((model) => model.available));
  const label = loading
    ? t('agentModel.loading')
    : saving
      ? 'Saving model...'
      : needsConfiguration
        ? t('agentModel.configure')
        : (selectedModel?.label ?? t('agentModel.label'));

  const handleTriggerClick = () => {
    if (needsConfiguration && onConfigureModel) {
      setOpen(false);
      onConfigureModel();
      return;
    }
    setOpen((prev) => !prev);
  };

  return (
    <div className={`model-menu model-menu--${variant}`} ref={rootRef}>
      <button
        type="button"
        className={[
          'model-menu__trigger',
          'base-select',
          open ? 'model-menu__trigger--open' : '',
          needsConfiguration ? 'model-menu__trigger--configure' : '',
        ].filter(Boolean).join(' ')}
        aria-haspopup={needsConfiguration ? 'dialog' : 'listbox'}
        aria-expanded={needsConfiguration ? undefined : open}
        aria-label={needsConfiguration ? t('agentModel.configure') : t('agentModel.label')}
        disabled={disabled}
        onClick={handleTriggerClick}
      >
        <SparkIcon />
        <span className="model-menu__value">{label}</span>
        {!needsConfiguration ? <ChevronIcon /> : null}
      </button>
      {open && (
        <ul className="model-menu__dropdown" role="listbox" aria-label={t('agentModel.label')}>
          {models.map((model) => {
            const optionDisabled = !model.available || saving;
            return (
              <li key={model.id} role="presentation">
                <button
                  type="button"
                  role="option"
                  aria-selected={selectedModelId === model.id}
                  aria-disabled={optionDisabled}
                  disabled={optionDisabled}
                  title={optionDisabled ? (model.unavailable_reason ?? t('agentModel.comingSoon')) : undefined}
                  className={[
                    'model-menu__option',
                    selectedModelId === model.id ? 'model-menu__option--active' : '',
                    optionDisabled ? 'model-menu__option--disabled' : '',
                  ]
                    .filter(Boolean)
                    .join(' ')}
                  onClick={() => {
                    if (optionDisabled) return;
                    void setSelectedModelId(model.id);
                    setOpen(false);
                  }}
                >
                  <span className="model-menu__option-label">{model.label}</span>
                  {optionDisabled && (
                    <span className="model-menu__option-badge">{model.unavailable_reason ?? t('agentModel.comingSoon')}</span>
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
