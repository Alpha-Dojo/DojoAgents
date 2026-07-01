import type { FolioPerformanceView } from '../types/folio';
import { FOLIO_MARKETS } from '../types/folio';
import type { MarketCode } from '../types/market';

export const FOLIO_CANDIDATE_INDEX_PREFIX = '__folio_candidate__';

export function folioCandidateIndexSymbol(market: MarketCode): string {
  return `${FOLIO_CANDIDATE_INDEX_PREFIX}${market}__`;
}

export function parseFolioCandidateIndexSymbol(symbol: string): MarketCode | null {
  if (!symbol.startsWith(FOLIO_CANDIDATE_INDEX_PREFIX) || !symbol.endsWith('__')) {
    return null;
  }
  const native = symbol.slice(FOLIO_CANDIDATE_INDEX_PREFIX.length, -2);
  return FOLIO_MARKETS.includes(native as MarketCode) ? (native as MarketCode) : null;
}

export function isFolioCandidateIndexSymbol(symbol: string | null | undefined): boolean {
  return Boolean(symbol && parseFolioCandidateIndexSymbol(symbol));
}

/** Candidate pools are overlay-only; never pass them as portfolio analysis benchmark params. */
export function portfolioAnalysisBenchmarkParam(
  symbol: string | null | undefined,
): string | undefined {
  if (!symbol || isFolioCandidateIndexSymbol(symbol)) return undefined;
  return symbol;
}

export function buildFolioCandidateIndexOptions(
  performance: FolioPerformanceView | null | undefined,
  labelForMarket: (market: MarketCode) => string,
): Array<{ symbol: string; label: string; market: MarketCode }> {
  if (!performance?.candidateSeriesByMarket) return [];
  return FOLIO_MARKETS.flatMap((market) => {
    const series = performance.candidateSeriesByMarket?.[market];
    if (!series?.length) return [];
    return [
      {
        symbol: folioCandidateIndexSymbol(market),
        label: labelForMarket(market),
        market,
      },
    ];
  });
}

export function resolveFolioBenchmarkLabel(
  symbol: string,
  option: { labelZh: string; labelEn: string } | null | undefined,
  labelForMarket: (market: MarketCode) => string,
  locale: 'zh' | 'en',
): string {
  const candidateMarket = parseFolioCandidateIndexSymbol(symbol);
  if (candidateMarket) {
    return labelForMarket(candidateMarket);
  }
  if (option) {
    return locale === 'zh' ? option.labelZh : option.labelEn;
  }
  return symbol;
}
