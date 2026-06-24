import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { searchFolioPortfolios } from '../../api/dojoFolio';
import { useTranslation } from '../../hooks/useTranslation';
import type { FolioPortfolioListItem } from '../../hooks/useFolioPortfolios';
import type { FolioPortfolioHoldingsPreview, FolioPortfolioSearchHit } from '../../utils/folioPortfolioSearch';
import { searchPortfoliosClient } from '../../utils/folioPortfolioSearch';

function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}

interface FolioPortfolioSearchProps {
  portfolios: FolioPortfolioListItem[];
  holdingsByPortfolioId: Record<string, FolioPortfolioHoldingsPreview[]>;
  onQueryChange: (query: string) => void;
  onSelectPortfolio: (id: string) => void;
}

export function FolioPortfolioSearch({
  portfolios,
  holdingsByPortfolioId,
  onQueryChange,
  onSelectPortfolio,
}: FolioPortfolioSearchProps) {
  const { t } = useTranslation();
  const listId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [focused, setFocused] = useState(false);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [apiHits, setApiHits] = useState<FolioPortfolioSearchHit[] | null>(null);
  const debouncedQuery = useDebouncedValue(query.trim(), 220);

  useEffect(() => {
    onQueryChange(debouncedQuery);
  }, [debouncedQuery, onQueryChange]);

  useEffect(() => {
    if (!debouncedQuery) {
      setApiHits(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    searchFolioPortfolios(debouncedQuery)
      .then((hits) => {
        if (!cancelled) setApiHits(hits);
      })
      .catch(() => {
        if (!cancelled) setApiHits(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [debouncedQuery]);

  useEffect(() => {
    if (!focused) return;
    const onPointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setFocused(false);
      }
    };
    document.addEventListener('mousedown', onPointerDown);
    return () => document.removeEventListener('mousedown', onPointerDown);
  }, [focused]);

  const clientHits = useMemo(
    () => searchPortfoliosClient(debouncedQuery, portfolios, holdingsByPortfolioId),
    [debouncedQuery, portfolios, holdingsByPortfolioId],
  );

  const hits = debouncedQuery ? (apiHits ?? clientHits) : [];

  const panelOpen = focused && debouncedQuery.length > 0;

  const handlePick = (portfolioId: string) => {
    onSelectPortfolio(portfolioId);
    setQuery('');
    onQueryChange('');
    setFocused(false);
    inputRef.current?.blur();
  };

  return (
    <div className="folio-portfolio-search" ref={rootRef}>
      <span className="folio-portfolio-search__icon" aria-hidden>
        ⌕
      </span>
      <input
        ref={inputRef}
        type="search"
        className="folio-portfolio-search__input"
        value={query}
        placeholder={t('folio.searchPlaceholder')}
        aria-controls={panelOpen ? listId : undefined}
        aria-expanded={panelOpen}
        aria-haspopup="listbox"
        onChange={(event) => setQuery(event.target.value)}
        onFocus={() => setFocused(true)}
      />

      {panelOpen ? (
        <div className="folio-portfolio-search__panel">
          <ul id={listId} className="folio-portfolio-search__list" role="listbox">
            {loading ? <li className="folio-portfolio-search__status">{t('folio.searching')}</li> : null}
            {!loading && hits.length === 0 ? (
              <li className="folio-portfolio-search__status">{t('folio.noSearchResults')}</li>
            ) : null}
            {!loading
              ? hits.map((hit) => {
                  const portfolio = portfolios.find((item) => item.id === hit.portfolioId);
                  if (!portfolio) return null;
                  return (
                    <li key={`${hit.portfolioId}:${hit.matchType}:${hit.matchedLabel ?? ''}`}>
                      <button
                        type="button"
                        className="folio-portfolio-search__option"
                        role="option"
                        onClick={() => handlePick(hit.portfolioId)}
                      >
                        <span className="folio-portfolio-search__option-name">{portfolio.name}</span>
                        <span className="folio-portfolio-search__option-meta">
                          {hit.matchType === 'name'
                            ? t('folio.searchMatchName')
                            : t('folio.searchMatchHolding', { label: hit.matchedLabel ?? '—' })}
                        </span>
                      </button>
                    </li>
                  );
                })
              : null}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
