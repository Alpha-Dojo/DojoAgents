import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { fetchCoreTickerSearch } from '../../api/dojoCore';
import { useDebouncedValue } from '../../hooks/useDebouncedValue';
import { useTranslation } from '../../hooks/useTranslation';
import type { MarketCode } from '../../types/dojoMesh';
import type { CoreTickerSearchItem } from '../../types/dojoCore';
import { SearchComboboxShell } from '../SearchComboboxShell';

const SEARCH_LIMIT = 20;

interface FolioAddHoldingSearchProps {
  market: MarketCode;
  existingTickers: Set<string>;
  onAdd: (ticker: string, market: MarketCode) => void;
  adding?: boolean;
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
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<CoreTickerSearchItem[]>([]);
  const debouncedQuery = useDebouncedValue(query.trim(), 220);

  useEffect(() => {
    if (!open) {
      setQuery('');
      setResults([]);
      setLoading(false);
    }
  }, [open]);

  useEffect(() => {
    if (!open || !debouncedQuery) {
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
  }, [debouncedQuery, market, open]);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onPointerDown);
    return () => document.removeEventListener('mousedown', onPointerDown);
  }, [open]);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  const visibleItems = useMemo(
    () => results.filter((item) => item.market === market && !existingTickers.has(item.ticker)),
    [existingTickers, market, results],
  );

  const handlePick = (item: CoreTickerSearchItem) => {
    onAdd(item.ticker, item.market);
    setOpen(false);
  };

  return (
    <div className="folio-add-holding" ref={rootRef}>
      {!open ? (
        <button
          type="button"
          className="action-button folio-add-holding__trigger"
          disabled={adding}
          onClick={() => setOpen(true)}
        >
          {t('folio.addHolding')}
        </button>
      ) : (
        <SearchComboboxShell
          className="folio-add-holding__search"
          inputRef={inputRef}
          iconClassName="folio-add-holding__icon"
          inputClassName="folio-add-holding__input"
          value={query}
          placeholder={t('folio.addHoldingPlaceholder')}
          controlsId={listId}
          expanded
          onChange={(event) => setQuery(event.target.value)}
        >
          <button
            type="button"
            className="folio-add-holding__cancel"
            aria-label={t('folio.cancel')}
            onClick={() => setOpen(false)}
          >
            ×
          </button>
          {debouncedQuery ? (
            <ul id={listId} className="search-combobox__panel search-combobox__list folio-add-holding__panel" role="listbox">
              {loading ? <li className="search-combobox__status folio-add-holding__status">{t('folio.searching')}</li> : null}
              {!loading && visibleItems.length === 0 ? (
                <li className="search-combobox__status folio-add-holding__status">{t('folio.noSearchResults')}</li>
              ) : null}
              {!loading
                ? visibleItems.map((item) => (
                    <li key={item.ticker}>
                      <button
                        type="button"
                        className="search-combobox__option folio-add-holding__option"
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
        </SearchComboboxShell>
      )}
    </div>
  );
}
