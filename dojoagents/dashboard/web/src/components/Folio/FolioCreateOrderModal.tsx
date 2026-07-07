import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { fetchEntityTickerSearch } from '../../api/entity';
import { useTranslation } from '../../hooks/useTranslation';
import type { MarketCode } from '../../types/market';
import type {
  FolioCreateOrderPayload,
  FolioOrderDraftContext,
  FolioOrderSide,
  FolioPositionActionTab,
  FolioPositionSyncPayload,
} from '../../types/folio';
import type { EntityTickerSearchItem } from '../../types/entity';
import { todayIsoDate } from '../../utils/folioStartDate';
import { fetchTickerOpenOnDate, formatOrderLimitPrice } from '../../utils/folioOrderPrice';
import { formatFolioOrderError } from '../../utils/folioOrderError';
import { localizedStockName } from '../../utils/stockDisplay';
import { DojoButton } from '../ui/DojoButton';
import { FolioStartDatePicker } from './FolioStartDatePicker';

const SEARCH_LIMIT = 20;

interface FolioCreateOrderModalProps {
  open: boolean;
  portfolioId: string;
  context: FolioOrderDraftContext | null;
  placing?: boolean;
  syncing?: boolean;
  onClose: () => void;
  onSubmit: (payload: FolioCreateOrderPayload) => Promise<void>;
  onSync?: (payload: FolioPositionSyncPayload) => Promise<void>;
}

function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}

export function FolioCreateOrderModal({
  open,
  context,
  placing = false,
  syncing = false,
  onClose,
  onSubmit,
  onSync,
}: FolioCreateOrderModalProps) {
  const { t, locale } = useTranslation();
  const listId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLDivElement>(null);
  const showSyncTab = Boolean(onSync);
  const [activeTab, setActiveTab] = useState<FolioPositionActionTab>('trade');
  const [market, setMarket] = useState<MarketCode>('us');
  const [ticker, setTicker] = useState('');
  const [tickerName, setTickerName] = useState('');
  const [orderSide, setOrderSide] = useState<FolioOrderSide>('buy');
  const [price, setPrice] = useState('');
  const [qty, setQty] = useState('');
  const [cost, setCost] = useState('');
  const [orderTime, setOrderTime] = useState(todayIsoDate());
  const [query, setQuery] = useState('');
  const [searchFocused, setSearchFocused] = useState(false);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchResults, setSearchResults] = useState<EntityTickerSearchItem[]>([]);
  const [priceLoading, setPriceLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const debouncedQuery = useDebouncedValue(query.trim(), 220);
  const tickerLocked = Boolean(context?.ticker);
  const syncDate = todayIsoDate();
  const submitting = placing || syncing;

  useEffect(() => {
    if (!open || !context) return;
    setMarket(context.market);
    setTicker(context.ticker ?? '');
    setTickerName(context.name ?? '');
    setOrderSide(context.orderSide ?? 'buy');
    setPrice(context.price != null && context.price > 0 ? String(context.price) : '');
    setQty(context.qty != null && context.qty >= 0 ? String(context.qty) : '');
    setCost(context.cost != null && context.cost > 0 ? String(context.cost) : '');
    setOrderTime(todayIsoDate());
    setQuery('');
    setError(null);
    setActiveTab(context.initialTab === 'sync' && showSyncTab ? 'sync' : 'trade');
  }, [context, open, showSyncTab]);

  useEffect(() => {
    if (!open || activeTab !== 'trade' || !ticker.trim() || !orderTime) return;

    let cancelled = false;
    setPriceLoading(true);
    void fetchTickerOpenOnDate(ticker.trim(), market, orderTime)
      .then((openPrice) => {
        if (cancelled || openPrice == null || !(openPrice > 0)) return;
        setPrice(formatOrderLimitPrice(openPrice));
      })
      .catch(() => {
        if (cancelled) return;
      })
      .finally(() => {
        if (!cancelled) setPriceLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [activeTab, market, open, orderTime, ticker]);

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose, open]);

  useEffect(() => {
    if (open) dialogRef.current?.focus();
  }, [open]);

  useEffect(() => {
    if (!open || tickerLocked || !debouncedQuery) {
      setSearchResults([]);
      setSearchLoading(false);
      return;
    }

    let cancelled = false;
    setSearchLoading(true);
    fetchEntityTickerSearch({
      q: debouncedQuery,
      market,
      limit: SEARCH_LIMIT,
    })
      .then((items) => {
        if (!cancelled) setSearchResults(items);
      })
      .catch(() => {
        if (!cancelled) setSearchResults([]);
      })
      .finally(() => {
        if (!cancelled) setSearchLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [debouncedQuery, market, open, tickerLocked]);

  useEffect(() => {
    const onPointerDown = (event: MouseEvent) => {
      if (!searchRef.current?.contains(event.target as Node)) {
        setSearchFocused(false);
      }
    };
    document.addEventListener('mousedown', onPointerDown);
    return () => document.removeEventListener('mousedown', onPointerDown);
  }, []);

  const visibleSearchItems = useMemo(
    () => searchResults.filter((item) => item.market === market),
    [market, searchResults],
  );

  const handlePickTicker = (item: EntityTickerSearchItem) => {
    setTicker(item.ticker);
    setTickerName(
      localizedStockName({ zh: item.name.zh, en: item.name.en, fallback: item.ticker }, locale),
    );
    setQuery('');
    setSearchFocused(false);
  };

  const handleClearTicker = () => {
    setTicker('');
    setTickerName('');
    setQuery('');
    setPrice('');
    setSearchFocused(false);
  };

  const showTickerDisplay = tickerLocked || Boolean(ticker.trim());

  const handleSubmitTrade = async () => {
    const parsedPrice = Number(price);
    const parsedQty = Number(qty);
    if (!ticker.trim()) {
      setError(t('folio.orderTickerRequired'));
      return;
    }
    if (!Number.isFinite(parsedPrice) || parsedPrice <= 0) {
      setError(t('folio.orderPriceRequired'));
      return;
    }
    if (!Number.isFinite(parsedQty) || parsedQty <= 0) {
      setError(t('folio.orderQtyRequired'));
      return;
    }

    setError(null);
    try {
      await onSubmit({
        ticker: ticker.trim(),
        market,
        orderSide,
        price: parsedPrice,
        qty: parsedQty,
        orderTime,
      });
      onClose();
    } catch (err: unknown) {
      setError(formatFolioOrderError(err, t, t('folio.orderSubmitFailed')));
    }
  };

  const handleSubmitSync = async () => {
    if (!onSync) return;
    const parsedCost = Number(cost);
    const parsedQty = Number(qty);
    if (!ticker.trim()) {
      setError(t('folio.orderTickerRequired'));
      return;
    }
    if (!Number.isFinite(parsedQty) || parsedQty < 0) {
      setError(t('folio.syncQtyRequired'));
      return;
    }
    if (parsedQty > 0 && (!Number.isFinite(parsedCost) || parsedCost <= 0)) {
      setError(t('folio.syncCostRequired'));
      return;
    }

    setError(null);
    try {
      await onSync({
        ticker: ticker.trim(),
        market,
        qty: parsedQty,
        cost: parsedQty > 0 ? parsedCost : 0,
      });
      onClose();
    } catch (err: unknown) {
      setError(formatFolioOrderError(err, t, t('folio.syncSubmitFailed')));
    }
  };

  const handleSubmit = () => {
    if (activeTab === 'sync') {
      void handleSubmitSync();
      return;
    }
    void handleSubmitTrade();
  };

  if (!open || !context) return null;

  const dialogTitleId = 'folio-position-action-dialog-title';

  return createPortal(
    <div className="folio-dialog" role="presentation">
      <button
        type="button"
        className="folio-dialog__backdrop"
        aria-label={t('folio.cancel')}
        onClick={onClose}
      />
      <div
        ref={dialogRef}
        className="folio-dialog__panel folio-dialog__panel--order"
        role="dialog"
        aria-modal="true"
        aria-labelledby={dialogTitleId}
        tabIndex={-1}
      >
        {showSyncTab ? (
          <div className="folio-order-form__mode-tabs" role="tablist" aria-label={t('folio.positionActionTabs')}>
            <button
              type="button"
              role="tab"
              id="folio-position-action-tab-trade"
              aria-selected={activeTab === 'trade'}
              aria-controls="folio-position-action-panel-trade"
              className={`folio-order-form__mode-tab${
                activeTab === 'trade' ? ' folio-order-form__mode-tab--active' : ''
              }`}
              onClick={() => {
                setActiveTab('trade');
                setError(null);
              }}
            >
              {t('folio.createOrder')}
            </button>
            <button
              type="button"
              role="tab"
              id="folio-position-action-tab-sync"
              aria-selected={activeTab === 'sync'}
              aria-controls="folio-position-action-panel-sync"
              className={`folio-order-form__mode-tab${
                activeTab === 'sync' ? ' folio-order-form__mode-tab--active' : ''
              }`}
              onClick={() => {
                setActiveTab('sync');
                setError(null);
              }}
            >
              {t('folio.syncPosition')}
            </button>
          </div>
        ) : (
          <h3 id={dialogTitleId} className="folio-dialog__title">
            {t('folio.createOrder')}
          </h3>
        )}

        {activeTab === 'sync' ? (
          <p className="folio-dialog__hint">{t('folio.syncPositionHint')}</p>
        ) : null}

        <div className="folio-order-form">
          <label className="folio-order-form__field">
            <span className="folio-order-form__label">{t('folio.colTicker')}</span>
            {showTickerDisplay ? (
              <div className="folio-order-form__ticker-readonly">
                <span className="folio-order-form__ticker-code">{ticker}</span>
                {tickerName ? <span className="folio-order-form__ticker-name">{tickerName}</span> : null}
                {!tickerLocked ? (
                  <button
                    type="button"
                    className="folio-order-form__ticker-clear"
                    aria-label={t('folio.changeOrderTicker')}
                    onClick={handleClearTicker}
                  >
                    ×
                  </button>
                ) : null}
              </div>
            ) : (
              <div className="folio-order-form__search" ref={searchRef}>
                <input
                  type="search"
                  className="folio-config__input folio-order-form__input"
                  value={query}
                  placeholder={t('folio.addHoldingPlaceholderShort')}
                  aria-controls={listId}
                  aria-expanded={searchFocused && debouncedQuery.length > 0}
                  onFocus={() => setSearchFocused(true)}
                  onChange={(event) => setQuery(event.target.value)}
                />
                {searchFocused && debouncedQuery ? (
                  <ul id={listId} className="folio-order-form__results" role="listbox">
                    {searchLoading ? (
                      <li className="folio-order-form__status">{t('folio.searching')}</li>
                    ) : null}
                    {!searchLoading && visibleSearchItems.length === 0 ? (
                      <li className="folio-order-form__status">{t('folio.noSearchResults')}</li>
                    ) : null}
                    {!searchLoading
                      ? visibleSearchItems.map((item) => (
                          <li key={item.ticker} role="presentation">
                            <button
                              type="button"
                              className="folio-order-form__result"
                              role="option"
                              onClick={() => handlePickTicker(item)}
                            >
                              <span>{item.ticker}</span>
                              <span>
                                {localizedStockName(
                                  { zh: item.name.zh, en: item.name.en, fallback: item.ticker },
                                  locale,
                                )}
                              </span>
                            </button>
                          </li>
                        ))
                      : null}
                  </ul>
                ) : null}
              </div>
            )}
          </label>

          {activeTab === 'trade' ? (
            <>
              <label className="folio-order-form__field">
                <span className="folio-order-form__label">{t('folio.orderSide')}</span>
                <div className="folio-order-form__side-toggle">
                  <button
                    type="button"
                    className={`folio-order-form__side${
                      orderSide === 'buy' ? ' folio-order-form__side--active folio-order-form__side--buy' : ''
                    }`}
                    onClick={() => setOrderSide('buy')}
                  >
                    {t('folio.orderBuy')}
                  </button>
                  <button
                    type="button"
                    className={`folio-order-form__side${
                      orderSide === 'sell' ? ' folio-order-form__side--active folio-order-form__side--sell' : ''
                    }`}
                    onClick={() => setOrderSide('sell')}
                  >
                    {t('folio.orderSell')}
                  </button>
                </div>
              </label>

              <label className="folio-order-form__field">
                <span className="folio-order-form__label">{t('folio.colPrice')}</span>
                <input
                  type="number"
                  min={0}
                  step="0.01"
                  className="folio-config__input folio-order-form__input"
                  value={price}
                  placeholder={priceLoading ? t('folio.orderPriceLoading') : undefined}
                  onChange={(event) => setPrice(event.target.value)}
                />
              </label>

              <label className="folio-order-form__field">
                <span className="folio-order-form__label">{t('folio.orderQty')}</span>
                <input
                  type="number"
                  min={0}
                  step="1"
                  className="folio-config__input folio-order-form__input"
                  value={qty}
                  onChange={(event) => setQty(event.target.value)}
                />
              </label>

              <label className="folio-order-form__field">
                <span className="folio-order-form__label">{t('folio.orderDate')}</span>
                <FolioStartDatePicker value={orderTime} onChange={setOrderTime} />
              </label>
            </>
          ) : (
            <>
              <label className="folio-order-form__field">
                <span className="folio-order-form__label">{t('folio.colShares')}</span>
                <input
                  type="number"
                  min={0}
                  step="1"
                  className="folio-config__input folio-order-form__input"
                  value={qty}
                  onChange={(event) => setQty(event.target.value)}
                />
              </label>

              <label className="folio-order-form__field">
                <span className="folio-order-form__label">{t('folio.colCost')}</span>
                <input
                  type="number"
                  min={0}
                  step="0.01"
                  className="folio-config__input folio-order-form__input"
                  value={cost}
                  onChange={(event) => setCost(event.target.value)}
                />
              </label>

              <label className="folio-order-form__field">
                <span className="folio-order-form__label">{t('folio.syncTime')}</span>
                <input
                  type="text"
                  className="folio-config__input folio-order-form__input folio-order-form__input--readonly"
                  value={syncDate}
                  readOnly
                />
              </label>
            </>
          )}

          {error ? <p className="folio-order-form__error">{error}</p> : null}
        </div>

        <div className="folio-dialog__actions">
          <DojoButton type="button" size="sm" variant="secondary" onClick={onClose} disabled={submitting}>
            {t('folio.cancel')}
          </DojoButton>
          <DojoButton
            type="button"
            size="sm"
            variant="primary"
            disabled={submitting}
            onClick={handleSubmit}
          >
            {activeTab === 'sync'
              ? syncing
                ? t('folio.syncSubmitting')
                : t('folio.syncSubmit')
              : placing
                ? t('folio.orderSubmitting')
                : t('folio.orderSubmit')}
          </DojoButton>
        </div>
      </div>
    </div>,
    document.body,
  );
}
