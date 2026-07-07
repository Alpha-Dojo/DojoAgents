import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
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

function orderChipTitle(order: FolioOrderEventView, displayName: string, eventMinute: string | null): string {
  if (order.syncNote) {
    return `${eventMinute ? `${eventMinute} · ` : ''}${displayName} · ${order.syncNote}`;
  }
  return eventMinute ? `${eventMinute} · ${displayName}` : displayName;
}

export function FolioOrderEventRail({
  date,
  side,
  orders,
  activeId,
  onClose,
}: FolioOrderEventRailProps) {
  const { t, locale } = useTranslation();
  const [detailsOpen, setDetailsOpen] = useState(false);
  const railRef = useRef<HTMLDivElement>(null);
  const trackRef = useRef<HTMLDivElement>(null);
  const measurerRef = useRef<HTMLDivElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);
  const moreBtnRef = useRef<HTMLButtonElement>(null);

  const [visibleCount, setVisibleCount] = useState<number>(orders.length);
  const [popoverStyle, setPopoverStyle] = useState<React.CSSProperties>({});

  const orderKey = orders.map((order) => order.id).join('|');

  const prevSelectionKeyRef = useRef<string>('');
  const isNewSelectionRef = useRef<boolean>(false);

  const currentSelectionKey = `${date}-${side}-${orderKey}`;
  if (prevSelectionKeyRef.current !== currentSelectionKey) {
    prevSelectionKeyRef.current = currentSelectionKey;
    isNewSelectionRef.current = true;
  }

  const visibleOrders = orders.slice(0, visibleCount);
  const hiddenOrders = orders.slice(visibleCount);

  const showSyncTime = side === 'sync' && orders.length > 1;
  const renderOrderChip = (order: FolioOrderEventView, compact = false) => {
    const displayName = resolveDisplayName(order, locale);
    const eventMinute = showSyncTime ? formatFolioOrderEventMinute(order.eventInstant) : null;
    const title = orderChipTitle(order, displayName, eventMinute);

    return (
      <div
        key={order.id}
        role="listitem"
        className={`folio-performance__order-event-chip folio-performance__order-event-chip--${order.side}${
          activeId === order.id ? ' folio-performance__order-event-chip--active' : ''
        }${compact ? ' folio-performance__order-event-chip--compact' : ''}`}
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
  };

  useLayoutEffect(() => {
    const measure = () => {
      const track = trackRef.current;
      const measurer = measurerRef.current;
      if (!track || !measurer) return;

      const containerWidth = Math.max(0, track.getBoundingClientRect().width - 30);
      const children = Array.from(measurer.children) as HTMLElement[];
      if (children.length === 0) return;

      const chipElements = children.slice(0, -1);
      const moreBtnElement = children[children.length - 1];

      const chipWidths = chipElements.map((el) => el.getBoundingClientRect().width);
      const moreWidth = moreBtnElement ? moreBtnElement.getBoundingClientRect().width : 30;
      const gap = 6;

      const totalCount = orders.length;

      let allFitWidth = 0;
      for (let i = 0; i < totalCount; i++) {
        allFitWidth += chipWidths[i] || 0;
        if (i > 0) allFitWidth += gap;
      }

      if (allFitWidth <= containerWidth) {
        setVisibleCount(totalCount);
        if (isNewSelectionRef.current) {
          isNewSelectionRef.current = false;
          setDetailsOpen(false);
        }
        return;
      }

      let k = totalCount - 1;
      for (; k >= 0; k--) {
        let neededWidth = 0;
        for (let i = 0; i < k; i++) {
          neededWidth += chipWidths[i] || 0;
          if (i > 0) neededWidth += gap;
        }
        if (k > 0) neededWidth += gap;
        neededWidth += moreWidth;

        if (neededWidth <= containerWidth) {
          break;
        }
      }

      const finalCount = Math.max(0, k);
      setVisibleCount(finalCount);

      if (isNewSelectionRef.current) {
        isNewSelectionRef.current = false;
        setDetailsOpen(totalCount > finalCount);
      }
    };

    measure();

    const track = trackRef.current;
    if (!track) return;
    const observer = new ResizeObserver(measure);
    observer.observe(track);

    return () => {
      observer.disconnect();
    };
  }, [orders, orderKey]);

  useEffect(() => {
    if (!detailsOpen) return;

    const updatePosition = () => {
      const track = trackRef.current;
      if (!track) return;
      const rect = track.getBoundingClientRect();
      const bodyRect = document.body.getBoundingClientRect();
      setPopoverStyle({
        position: 'absolute',
        zIndex: 9999,
        top: `${rect.bottom + window.scrollY + 6}px`,
        right: `${bodyRect.right - rect.right}px`,
        left: 'auto',
        width: 'max-content',
        maxWidth: `${Math.min(520, rect.width)}px`,
      });
    };

    updatePosition();
    window.addEventListener('resize', updatePosition);
    window.addEventListener('scroll', updatePosition, true);

    return () => {
      window.removeEventListener('resize', updatePosition);
      window.removeEventListener('scroll', updatePosition, true);
    };
  }, [detailsOpen, orders, orderKey]);

  useEffect(() => {
    if (!detailsOpen) return;

    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (
        !popoverRef.current?.contains(target) &&
        !moreBtnRef.current?.contains(target)
      ) {
        setDetailsOpen(false);
      }
    };

    document.addEventListener('pointerdown', handlePointerDown);
    return () => document.removeEventListener('pointerdown', handlePointerDown);
  }, [detailsOpen]);

  if (orders.length === 0) {
    return null;
  }

  return (
    <div ref={railRef} className="folio-performance__order-event-rail" aria-label={t('folio.orderEventRailLabel', { date })}>
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
      <div className="folio-performance__order-event-rail-scroll" ref={trackRef}>
        <div className="folio-performance__order-event-rail-track" role="list">
          {visibleOrders.map((order) => renderOrderChip(order, true))}
          {hiddenOrders.length > 0 ? (
            <button
              ref={moreBtnRef}
              type="button"
              className={`folio-performance__order-event-more${
                detailsOpen ? ' folio-performance__order-event-more--active' : ''
              }`}
              aria-expanded={detailsOpen}
              aria-label={t('folio.orderEventRailCount', { count: hiddenOrders.length })}
              onClick={() => setDetailsOpen((open) => !open)}
            >
              +{hiddenOrders.length}
            </button>
          ) : null}
        </div>

        {/* Hidden measurement container */}
        <div
          style={{
            position: 'absolute',
            width: 0,
            height: 0,
            overflow: 'hidden',
            visibility: 'hidden',
            pointerEvents: 'none',
          }}
          aria-hidden="true"
        >
          <div
            ref={measurerRef}
            style={{
              display: 'flex',
              gap: '6px',
              whiteSpace: 'nowrap',
              width: 'max-content',
            }}
          >
            {orders.map((order) => renderOrderChip(order, true))}
            <button
              type="button"
              className="folio-performance__order-event-more"
            >
              +{orders.length}
            </button>
          </div>
        </div>

        {detailsOpen && hiddenOrders.length > 0
          ? createPortal(
              <div
                ref={popoverRef}
                className="folio-performance__order-event-popover"
                style={popoverStyle}
                role="dialog"
                aria-label={t('folio.orderEventRailCount', { count: hiddenOrders.length })}
              >
                <div className="folio-performance__order-event-popover-list" role="list">
                  {hiddenOrders.map((order) => renderOrderChip(order))}
                </div>
              </div>,
              document.body
            )
          : null}
      </div>
    </div>
  );
}
