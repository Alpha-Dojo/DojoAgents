import { useEffect, useRef, useState } from 'react';
import { useTradingClock } from '../hooks/useTradingClock';
import { useTranslation } from '../hooks/useTranslation';
import {
  TRADING_TIMEZONES,
  type TradingTimezoneId,
} from '../timezone/tradingTimezone';
import './TradingClockSwitcher.css';

function ChevronIcon() {
  return (
    <svg
      className="tz-menu__chevron"
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

export function TradingClockSwitcher() {
  const { time, timezoneId, timezoneLabel, setTimezone } = useTradingClock();
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

  const selectTimezone = (id: TradingTimezoneId) => {
    setTimezone(id);
    setOpen(false);
  };

  return (
    <div className="tz-menu" ref={rootRef}>
      <button
        type="button"
        className={`tz-menu__trigger ${open ? 'tz-menu__trigger--open' : ''}`}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={t('timezone.label')}
        onClick={() => setOpen((prev) => !prev)}
      >
        <time className="tz-menu__time" dateTime={time}>
          {time}
        </time>
        <span className="tz-menu__label">{timezoneLabel}</span>
        <ChevronIcon />
      </button>
      {open && (
        <ul className="tz-menu__dropdown" role="listbox" aria-label={t('timezone.label')}>
          {TRADING_TIMEZONES.map((tz) => (
            <li key={tz.id} role="presentation">
              <button
                type="button"
                role="option"
                aria-selected={timezoneId === tz.id}
                className={`tz-menu__option ${timezoneId === tz.id ? 'tz-menu__option--active' : ''}`}
                onClick={() => selectTimezone(tz.id)}
              >
                <span className="tz-menu__option-label">{tz.label}</span>
                <span className="tz-menu__option-city">{t(`timezone.${tz.id}`)}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
