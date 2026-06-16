import { useEffect, useState } from 'react';
import {
  formatTradingClock,
  getTradingTimezone,
  readStoredTradingTimezone,
  storeTradingTimezone,
  type TradingTimezoneId,
} from '../timezone/tradingTimezone';

export function useTradingClock() {
  const [timezoneId, setTimezoneId] = useState<TradingTimezoneId>(readStoredTradingTimezone);
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const tick = () => setNow(new Date());
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, []);

  const setTimezone = (id: TradingTimezoneId) => {
    storeTradingTimezone(id);
    setTimezoneId(id);
  };

  const timezone = getTradingTimezone(timezoneId);

  return {
    time: formatTradingClock(now, timezoneId),
    timezoneId,
    timezoneLabel: timezone.label,
    setTimezone,
  };
}
