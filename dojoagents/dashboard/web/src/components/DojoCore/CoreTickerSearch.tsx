import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { fetchCoreTickerSearch } from '../../api/dojoCore';
import { fetchSectorConstituents } from '../../api/dojoSphere';
import { useDebouncedValue } from '../../hooks/useDebouncedValue';
import { useTranslation } from '../../hooks/useTranslation';
import type { MarketCode } from '../../types/dojoMesh';
import type { CoreTickerSearchItem } from '../../types/dojoCore';
import type { SectorPathSelection } from '../../types/sectorTaxonomy';
import { MARKET_FLAG } from '../../utils/marketDisplay';
import { sortCoreTickerItems } from '../../utils/coreTickerSort';
import { SearchComboboxShell } from '../SearchComboboxShell';

const MARKETS: MarketCode[] = ['us', 'sh', 'hk'];
const SEARCH_LIMIT = 30;

interface CoreTickerSearchProps {
  ticker: string;
  market: MarketCode;
  selection: SectorPathSelection | null;
  onSelect: (item: CoreTickerSearchItem) => void;
}

function toSearchItem(item: {
  ticker: string;
  market: MarketCode;
  name: { zh: string; en: string };
  market_cap?: number | null;
}): CoreTickerSearchItem {
  return {
    ticker: item.ticker,
    market: item.market,
    name: item.name,
    market_cap: item.market_cap ?? 0,
  };
}

export function CoreTickerSearch({ ticker, market, selection, onSelect }: CoreTickerSearchProps) {
  const { t, locale } = useTranslation();
  const listId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [focused, setFocused] = useState(false);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [defaults, setDefaults] = useState<CoreTickerSearchItem[]>([]);
  const [results, setResults] = useState<CoreTickerSearchItem[]>([]);
  const debouncedQuery = useDebouncedValue(query.trim(), 220);

  const panelOpen = focused;

  useEffect(() => {
    if (!panelOpen || !selection?.level1Id || !selection.level2Id || !selection.level3Id) {
      setDefaults([]);
      return;
    }
    let cancelled = false;
    const params = {
      level1Id: selection.level1Id,
      level2Id: selection.level2Id,
      level3Id: selection.level3Id,
      scope: 'L3' as const,
    };
    Promise.all(MARKETS.map((marketCode) => fetchSectorConstituents({ ...params, market: marketCode })))
      .then((responses) => {
        if (cancelled) return;
        const merged = sortCoreTickerItems(responses.flatMap((response) => response.items.map(toSearchItem)));
        setDefaults(merged);
      })
      .catch(() => {
        if (!cancelled) setDefaults([]);
      });
    return () => {
      cancelled = true;
    };
  }, [panelOpen, selection?.level1Id, selection?.level2Id, selection?.level3Id]);

  useEffect(() => {
    if (!panelOpen || !debouncedQuery) {
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
  }, [debouncedQuery, panelOpen]);

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

  const visibleItems = useMemo(
    () => (debouncedQuery ? results : defaults),
    [debouncedQuery, results, defaults],
  );

  const handlePick = (item: CoreTickerSearchItem) => {
    onSelect(item);
    setQuery('');
    setFocused(false);
    inputRef.current?.blur();
  };

  return (
    <SearchComboboxShell
      className="core-ticker-search"
      rootRef={rootRef}
      inputRef={inputRef}
      iconClassName="core-ticker-search__icon"
      inputClassName="core-ticker-search__input"
      value={query}
      placeholder={t('core.tickerSearchPlaceholder')}
      controlsId={panelOpen ? listId : undefined}
      expanded={panelOpen}
      onChange={(event) => setQuery(event.target.value)}
      onFocus={() => setFocused(true)}
    >
      {panelOpen ? (
        <div className="search-combobox__panel core-ticker-search__panel">
          <ul id={listId} className="search-combobox__list core-ticker-search__list" role="listbox">
            {loading ? <li className="search-combobox__status core-ticker-search__status">{t('core.searching')}</li> : null}
            {!loading && visibleItems.length === 0 ? (
              <li className="search-combobox__status core-ticker-search__status">{t('core.noSearchResults')}</li>
            ) : null}
            {!loading
              ? visibleItems.map((item) => (
                  <li key={`${item.market}:${item.ticker}`}>
                    <button
                      type="button"
                      className="search-combobox__option core-ticker-search__option"
                      role="option"
                      aria-selected={item.ticker === ticker && item.market === market}
                      onClick={() => handlePick(item)}
                    >
                      <span className="core-ticker-search__option-flag" aria-hidden>
                        {MARKET_FLAG[item.market]}
                      </span>
                      <span className="core-ticker-search__option-ticker">{item.ticker}</span>
                      <span className="core-ticker-search__option-name">
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
    </SearchComboboxShell>
  );
}
