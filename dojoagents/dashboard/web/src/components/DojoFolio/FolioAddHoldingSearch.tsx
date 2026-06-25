import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { fetchCoreTickerSearch } from '../../api/dojoCore';
import { useTranslation } from '../../hooks/useTranslation';
import type { MarketCode } from '../../types/dojoMesh';
import type { CoreTickerSearchItem } from '../../types/dojoCore';

const SEARCH_LIMIT = 20;

interface FolioAddHoldingSearchProps {
  market: MarketCode;
  existingTickers: Set<string>;
  onAdd: (ticker: string, market: MarketCode) => void;
  adding?: boolean;
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
}: FolioAddHoldingSearchProps) {
  const { t, locale } = useTranslation();
  const listId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState('');
  const [focused, setFocused] = useState(false);
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<CoreTickerSearchItem[]>([]);
  const debouncedQuery = useDebouncedValue(query.trim(), 220);

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

  useEffect(() => {
    const onPointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
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

  const handlePick = (item: CoreTickerSearchItem) => {
    onAdd(item.ticker, item.market);
    setQuery('');
    setFocused(false);
    inputRef.current?.blur();
  };

  const clearQuery = () => {
    setQuery('');
    inputRef.current?.focus();
  };

  return (
    <div className="folio-add-holding folio-add-holding--inline" ref={rootRef}>
      <div className="folio-add-holding__search">
        <span className="folio-add-holding__icon" aria-hidden>
          ⌕
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
          >
            ×
          </button>
        ) : null}
        {showPanel ? (
          <ul id={listId} className="folio-add-holding__panel" role="listbox">
            {loading ? <li className="folio-add-holding__status">{t('folio.searching')}</li> : null}
            {!loading && visibleItems.length === 0 ? (
              <li className="folio-add-holding__status">{t('folio.noSearchResults')}</li>
            ) : null}
            {!loading
              ? visibleItems.map((item) => (
                  <li key={item.ticker}>
                    <button
                      type="button"
                      className="folio-add-holding__option"
                      role="option"
                      disabled={adding}
                      onClick={() => handlePick(item)}
                    >
                      <span className="folio-add-holding__option-ticker">{item.ticker}</span>
                      <span className="folio-add-holding__option-name">
                        {locale === 'zh'
                          ? item.name.zh || item.name.en
                          : item.name.en || item.name.zh}
                      </span>
                    </button>
                  </li>
                ))
              : null}
          </ul>
        ) : null}
      </div>
    </div>
  );
}
