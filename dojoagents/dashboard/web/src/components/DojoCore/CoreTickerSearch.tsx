import { useEffect, useId, useRef, useState } from 'react';
import { fetchCoreTickerSearch } from '../../api/dojoCore';
import { useTranslation } from '../../hooks/useTranslation';
import type { MarketCode } from '../../types/dojoMesh';
import type { CoreTickerSearchItem } from '../../types/dojoCore';
import { MARKET_FLAG_IMAGE } from '../../utils/marketDisplay';

const SEARCH_LIMIT = 30;

interface CoreTickerSearchProps {
  ticker: string;
  market: MarketCode;
  onSelect: (item: CoreTickerSearchItem) => void;
}

function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}

export function CoreTickerSearch({ ticker, market, onSelect }: CoreTickerSearchProps) {
  const { t, locale } = useTranslation();
  const listId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [focused, setFocused] = useState(false);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<CoreTickerSearchItem[]>([]);
  const debouncedQuery = useDebouncedValue(query.trim(), 220);

  const panelOpen = focused && debouncedQuery.length > 0;

  useEffect(() => {
    if (!debouncedQuery) {
      setResults([]);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    fetchCoreTickerSearch({
      q: debouncedQuery,
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
  }, [debouncedQuery]);

  useEffect(() => {
    if (!panelOpen) return;
    const onPointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setFocused(false);
      }
    };
    document.addEventListener('mousedown', onPointerDown);
    return () => document.removeEventListener('mousedown', onPointerDown);
  }, [panelOpen]);

  const handlePick = (item: CoreTickerSearchItem) => {
    onSelect(item);
    setQuery('');
    setFocused(false);
    inputRef.current?.blur();
  };

  const clearQuery = () => {
    setQuery('');
    inputRef.current?.focus();
  };

  return (
    <div className="core-ticker-search" ref={rootRef}>
      <span className="core-ticker-search__icon" aria-hidden>
        ⌕
      </span>
      <input
        ref={inputRef}
        type="search"
        className="core-ticker-search__input base-search-input"
        value={query}
        placeholder={t('core.tickerSearchPlaceholder')}
        aria-controls={panelOpen ? listId : undefined}
        aria-expanded={panelOpen}
        aria-haspopup="listbox"
        onChange={(event) => setQuery(event.target.value)}
        onFocus={() => setFocused(true)}
      />
      {query ? (
        <button
          type="button"
          className="core-ticker-search__clear"
          aria-label={t('folio.cancel')}
          onClick={clearQuery}
        />
      ) : null}

      {panelOpen ? (
        <div className="core-ticker-search__panel dojo-dropdown-select__dropdown">
          <ul id={listId} className="core-ticker-search__list" role="listbox">
            {loading ? <li className="core-ticker-search__status">{t('core.searching')}</li> : null}
            {!loading && results.length === 0 ? (
              <li className="core-ticker-search__status">{t('core.noSearchResults')}</li>
            ) : null}
            {!loading
              ? results.map((item) => (
                  <li key={`${item.market}:${item.ticker}`} role="presentation">
                    <button
                      type="button"
                      className="core-ticker-search__option dojo-dropdown-select__option"
                      role="option"
                      aria-selected={item.ticker === ticker && item.market === market}
                      onClick={() => handlePick(item)}
                    >
                      <img className="core-ticker-search__option-flag" src={MARKET_FLAG_IMAGE[item.market]} alt="" aria-hidden />
                      <span className="core-ticker-search__option-ticker dojo-dropdown-select__option-label">{item.ticker}</span>
                      <span className="core-ticker-search__option-name dojo-dropdown-select__option-detail">
                        {locale === 'zh'
                          ? item.name.zh || item.name.en
                          : item.name.en || item.name.zh}
                      </span>
                    </button>
                  </li>
                ))
              : null}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
