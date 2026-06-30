import type { CSSProperties } from 'react';
import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { fetchEntityTickerSearch } from '../../api/entity';
import { useTranslation } from '../../hooks/useTranslation';
import type { MarketCode } from '../../types/market';
import type { EntityTickerSearchItem } from '../../types/entity';

const SEARCH_LIMIT = 20;
const PANEL_GAP = 6;
const PANEL_MAX_HEIGHT = 220;
const PANEL_MIN_HEIGHT = 80;
const VIEWPORT_PADDING = 8;

interface FolioAddHoldingSearchProps {
  market: MarketCode;
  existingTickers: Set<string>;
  onAdd: (ticker: string, market: MarketCode) => void;
  adding?: boolean;
  /** `trailing` — right side of market header, slightly wider */
  placement?: 'inline' | 'trailing';
}

function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}

export function FolioAddHoldingSearch({
  market,
  existingTickers,
  onAdd,
  adding = false,
  placement = 'inline',
}: FolioAddHoldingSearchProps) {
  const { t, locale } = useTranslation();
  const listId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLUListElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [panelStyle, setPanelStyle] = useState<CSSProperties>({});
  const [query, setQuery] = useState('');
  const [focused, setFocused] = useState(false);
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<EntityTickerSearchItem[]>([]);
  const debouncedQuery = useDebouncedValue(query.trim(), 220);

  useEffect(() => {
    if (!debouncedQuery) {
      setResults([]);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    fetchEntityTickerSearch({
      q: debouncedQuery,
      market,
      limit: SEARCH_LIMIT,
    })
      .then((items) => {
        if (!cancelled) setResults(items);
      })
      .catch(() => {
        if (!cancelled) setResults([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [debouncedQuery, market]);

  const updatePanelPosition = useCallback(() => {
    const rect = rootRef.current?.getBoundingClientRect();
    if (!rect) return;

    const width = Math.min(Math.max(rect.width, 220), 280);
    const left = Math.max(
      VIEWPORT_PADDING,
      Math.min(rect.left, window.innerWidth - width - VIEWPORT_PADDING),
    );
    const panelScrollHeight = panelRef.current?.scrollHeight ?? PANEL_MAX_HEIGHT;
    const desiredHeight = Math.min(panelScrollHeight, PANEL_MAX_HEIGHT);
    const availableBelow = window.innerHeight - rect.bottom - PANEL_GAP - VIEWPORT_PADDING;
    const availableAbove = rect.top - PANEL_GAP - VIEWPORT_PADDING;
    const openAbove = availableBelow < desiredHeight && availableAbove > availableBelow;
    const availableHeight = Math.max(
      PANEL_MIN_HEIGHT,
      openAbove ? availableAbove : availableBelow,
    );
    const maxHeight = Math.min(PANEL_MAX_HEIGHT, panelScrollHeight, availableHeight);
    const top = openAbove
      ? Math.max(VIEWPORT_PADDING, rect.top - PANEL_GAP - maxHeight)
      : rect.bottom + PANEL_GAP;

    setPanelStyle({
      left,
      maxHeight,
      minWidth: width,
      top,
      width,
    });
  }, []);

  useEffect(() => {
    const onPointerDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (
        !rootRef.current?.contains(target) &&
        !panelRef.current?.contains(target)
      ) {
        setFocused(false);
      }
    };
    document.addEventListener('mousedown', onPointerDown);
    return () => document.removeEventListener('mousedown', onPointerDown);
  }, []);

  const visibleItems = useMemo(
    () => results.filter((item) => item.market === market && !existingTickers.has(item.ticker)),
    [existingTickers, market, results],
  );

  const showPanel = focused && debouncedQuery.length > 0;

  useEffect(() => {
    if (!showPanel) return;

    const handleViewportChange = () => updatePanelPosition();

    updatePanelPosition();
    window.addEventListener('resize', handleViewportChange);
    window.addEventListener('scroll', handleViewportChange, true);
    return () => {
      window.removeEventListener('resize', handleViewportChange);
      window.removeEventListener('scroll', handleViewportChange, true);
    };
  }, [loading, showPanel, updatePanelPosition, visibleItems.length]);

  const handlePick = (item: EntityTickerSearchItem) => {
    onAdd(item.ticker, item.market);
    setQuery('');
    setFocused(false);
    inputRef.current?.blur();
  };

  const clearQuery = () => {
    setQuery('');
    inputRef.current?.focus();
  };

  const panel = showPanel
    ? createPortal(
        <ul
          id={listId}
          className="folio-add-holding__panel dojo-dropdown-select__dropdown"
          role="listbox"
          ref={panelRef}
          style={panelStyle}
        >
          {loading ? <li className="folio-add-holding__status">{t('folio.searching')}</li> : null}
          {!loading && visibleItems.length === 0 ? (
            <li className="folio-add-holding__status">{t('folio.noSearchResults')}</li>
          ) : null}
          {!loading
            ? visibleItems.map((item) => (
                <li key={item.ticker} role="presentation">
                  <button
                    type="button"
                    className="folio-add-holding__option dojo-dropdown-select__option"
                    role="option"
                    disabled={adding}
                    onClick={() => handlePick(item)}
                  >
                    <span className="folio-add-holding__option-ticker dojo-dropdown-select__option-label">{item.ticker}</span>
                    <span className="folio-add-holding__option-name dojo-dropdown-select__option-detail">
                      {locale === 'zh'
                        ? item.name.zh || item.name.en
                        : item.name.en || item.name.zh}
                    </span>
                  </button>
                </li>
              ))
            : null}
        </ul>,
        document.body,
      )
    : null;

  return (
    <div
      className={`folio-add-holding folio-add-holding--${placement}`}
      ref={rootRef}
    >
      <div className="folio-add-holding__search">
        <span className="folio-add-holding__icon" aria-hidden>
        </span>
        <input
          ref={inputRef}
          type="search"
          className="folio-add-holding__input"
          value={query}
          placeholder={t('folio.addHoldingPlaceholderShort')}
          aria-controls={listId}
          aria-expanded={showPanel}
          aria-haspopup="listbox"
          disabled={adding}
          onFocus={() => setFocused(true)}
          onChange={(event) => setQuery(event.target.value)}
        />
        {query ? (
          <button
            type="button"
            className="folio-add-holding__clear"
            aria-label={t('folio.cancel')}
            onClick={clearQuery}
          />
        ) : null}
        {panel}
      </div>
    </div>
  );
}
