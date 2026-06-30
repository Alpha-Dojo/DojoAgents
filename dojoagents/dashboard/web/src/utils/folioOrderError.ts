import { ApiError, parseApiErrorMessage } from '../api/http';

type TranslateFn = (key: string, params?: Record<string, string | number>) => string;

interface FolioOrderErrorDetail {
  message?: string;
  code?: string;
  context?: Record<string, unknown>;
}

function readOrderErrorDetail(err: unknown): FolioOrderErrorDetail | null {
  if (!(err instanceof ApiError)) return null;
  if (typeof err.body !== 'object' || err.body === null || !('detail' in err.body)) return null;
  const detail = (err.body as { detail: unknown }).detail;
  if (typeof detail !== 'object' || detail === null) return null;
  return detail as FolioOrderErrorDetail;
}

function formatNumber(value: unknown, digits = 4): string {
  const parsed = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(parsed)) return '—';
  return parsed.toFixed(digits).replace(/\.?0+$/, '');
}

export function formatFolioOrderError(err: unknown, t: TranslateFn, fallback: string): string {
  const detail = readOrderErrorDetail(err);
  if (!detail) {
    return parseApiErrorMessage(err, fallback);
  }

  const context = detail.context ?? {};
  switch (detail.code) {
    case 'insufficient_shares': {
      const held = Number(context.held);
      if (!Number.isFinite(held) || held <= 0) {
        return t('folio.orderErrorNoPosition');
      }
      return t('folio.orderErrorInsufficientShares', {
        held: formatNumber(held),
        requested: formatNumber(context.requested),
      });
    }
    case 'price_out_of_range':
      return t('folio.orderErrorPriceOutOfRange', {
        price: formatNumber(context.price, 2),
        date: String(context.date ?? ''),
        low: formatNumber(context.low, 2),
        high: formatNumber(context.high, 2),
      });
    case 'no_trading_bar':
      return t('folio.orderErrorNoTradingBar', {
        ticker: String(context.ticker ?? ''),
        date: String(context.date ?? ''),
      });
    case 'no_kline_data':
      return t('folio.orderErrorNoKlineData', {
        ticker: String(context.ticker ?? ''),
      });
    case 'no_trading_day':
      return t('folio.orderErrorNoTradingDay', {
        ticker: String(context.ticker ?? ''),
        date: String(context.date ?? ''),
      });
    case 'insufficient_cash':
      return t('folio.orderErrorInsufficientCash', {
        available: formatNumber(context.available, 2),
        required: formatNumber(context.required, 2),
      });
    case 'invalid_order':
      return t('folio.orderErrorInvalidOrder');
    case 'not_filled':
      return t('folio.orderErrorNotFilled');
    default:
      break;
  }

  if (typeof detail.message === 'string' && detail.message.trim()) {
    return detail.message.trim();
  }
  return parseApiErrorMessage(err, fallback);
}
