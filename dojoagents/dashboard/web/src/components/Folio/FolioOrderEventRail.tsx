import { useTranslation } from '../../hooks/useTranslation';
import {
  formatFolioOrderEventMinute,
  type FolioOrderEventView,
  type FolioOrderMarkerSide,
} from '../../utils/folioOrderMarkers';
import { formatStockPrice } from '../../utils/marketStats';
import { MARKET_CODE } from '../../utils/marketDisplay';

interface FolioOrderEventRailProps {
  date: string;
  side: FolioOrderMarkerSide;
  orders: FolioOrderEventView[];
  activeId: string | null;
  onClose: () => void;
}

function resolveDisplayName(order: FolioOrderEventView, locale: 'zh' | 'en'): string {
  if (locale === 'zh' && order.nameZh) return order.nameZh;
  if (order.nameEn) return order.nameEn;
  return order.name;
}

function sideTitleKey(side: FolioOrderMarkerSide): 'folio.orderBuy' | 'folio.orderSell' | 'folio.orderSync' {
  if (side === 'sell') return 'folio.orderSell';
  if (side === 'sync') return 'folio.orderSync';
  return 'folio.orderBuy';
}

export function FolioOrderEventRail({
  date,
  side,
  orders,
  activeId,
  onClose,
}: FolioOrderEventRailProps) {
  const { t, locale } = useTranslation();

  if (orders.length === 0) {
    return null;
  }

  const showSyncTime = side === 'sync' && orders.length > 1;

  return (
    <div className="folio-performance__order-event-rail" aria-label={t('folio.orderEventRailLabel', { date })}>
      <div className={`folio-performance__order-event-rail-head folio-performance__order-event-rail-head--${side}`}>
        <span className={`folio-performance__order-event-rail-icon folio-performance__order-event-rail-icon--${side}`} aria-hidden />
        <span className="folio-performance__order-event-rail-title">{t(sideTitleKey(side))}</span>
        <span className="folio-performance__order-event-rail-date">{date}</span>
        <span className="folio-performance__order-event-rail-count">
          {t('folio.orderEventRailCount', { count: orders.length })}
        </span>
        <button
          type="button"
          className="folio-performance__order-event-rail-close"
          aria-label={t('folio.orderEventRailClose')}
          onClick={onClose}
        >
          ×
        </button>
      </div>
      <div className="folio-performance__order-event-rail-scroll">
        <div className="folio-performance__order-event-rail-track" role="list">
        {orders.map((order) => {
          const displayName = resolveDisplayName(order, locale);
          const eventMinute = showSyncTime ? formatFolioOrderEventMinute(order.eventInstant) : null;
          const title = order.syncNote
            ? `${eventMinute ? `${eventMinute} · ` : ''}${displayName} · ${order.syncNote}`
            : eventMinute
              ? `${eventMinute} · ${displayName}`
              : displayName;
          return (
            <div
              key={order.id}
              role="listitem"
              className={`folio-performance__order-event-chip folio-performance__order-event-chip--${order.side}${
                activeId === order.id ? ' folio-performance__order-event-chip--active' : ''
              }`}
              title={title}
            >
              {eventMinute ? (
                <>
                  <span className="folio-performance__order-event-chip-time">{eventMinute}</span>
                  <span className="folio-performance__order-event-chip-sep" aria-hidden>
                    ·
                  </span>
                </>
              ) : null}
              <span className="folio-performance__order-event-chip-market">{MARKET_CODE[order.market]}</span>
              <span className="folio-performance__order-event-chip-ticker">{order.ticker}</span>
              <span className="folio-performance__order-event-chip-name">{displayName}</span>
              <span className="folio-performance__order-event-chip-sep" aria-hidden>
                ·
              </span>
              <span className="folio-performance__order-event-chip-qty">
                {order.side === 'sync' && order.qty <= 0
                  ? t('folio.orderSyncClear')
                  : t('folio.orderSyncQty', { qty: order.qty })}
              </span>
              {order.qty > 0 ? (
                <>
                  <span className="folio-performance__order-event-chip-sep" aria-hidden>
                    ·
                  </span>
                  <span className="folio-performance__order-event-chip-price">
                    {formatStockPrice(order.price)}
                  </span>
                </>
              ) : null}
            </div>
          );
        })}
        </div>
      </div>
    </div>
  );
}
