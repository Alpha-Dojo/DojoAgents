export interface AgentToolResultData {
  portfolio_id?: string;
  name?: string;
  holdings_count?: number;
  holdings_by_market?: Record<string, number>;
  tickers?: string[];
}

function formatMarketCounts(counts: Record<string, number>, locale: 'zh' | 'en'): string {
  const parts = Object.entries(counts)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([market, count]) => `${market.toUpperCase()}×${count}`);
  if (parts.length === 0) return '';
  return locale === 'zh' ? `分市场 ${parts.join(' · ')}` : `By market ${parts.join(' · ')}`;
}

function previewTickers(tickers: string[], limit = 6): string {
  if (tickers.length === 0) return '';
  const head = tickers.slice(0, limit).join(', ');
  if (tickers.length <= limit) return head;
  return `${head} +${tickers.length - limit}`;
}

export function formatToolArguments(
  tool: string,
  args: Record<string, unknown> | undefined,
  locale: 'zh' | 'en',
): string | null {
  if (!args || Object.keys(args).length === 0) return null;

  const ticker = typeof args.ticker === 'string' ? args.ticker : null;
  const market = typeof args.market === 'string' ? args.market.toUpperCase() : null;
  const action = typeof args.action === 'string' ? args.action : null;
  const name = typeof args.name === 'string' ? args.name : null;
  const portfolioId =
    typeof args.portfolio_id === 'string' ? args.portfolio_id.slice(0, 12) : null;
  const strategy =
    typeof args.allocation_strategy === 'string' ? args.allocation_strategy : null;
  const holdings = Array.isArray(args.holdings) ? args.holdings : null;

  switch (tool) {
    case 'get_ticker_financials':
    case 'get_ticker_realtime_quote':
    case 'get_ticker_price_trends':
    case 'get_ticker_news_and_events':
      if (ticker && market) return `${ticker} · ${market}`;
      if (ticker) return ticker;
      return null;
    case 'filter_sector_constituents':
      return market ? `${locale === 'zh' ? '市场' : 'Market'} ${market}` : null;
    case 'screen_market_stocks': {
      const bits: string[] = [];
      if (market) bits.push(market);
      const days = args.days;
      if (typeof days === 'number') {
        bits.push(
          days === 0
            ? locale === 'zh'
              ? '总涨跌'
              : 'total'
            : `${days}${locale === 'zh' ? '日' : 'D'}`,
        );
      }
      if (typeof args.min_return_pct === 'number') {
        bits.push(
          locale === 'zh'
            ? `涨幅≥${args.min_return_pct}%`
            : `ret≥${args.min_return_pct}%`,
        );
      }
      if (typeof args.min_market_cap === 'number') {
        const capB = (args.min_market_cap as number) / 1e9;
        bits.push(locale === 'zh' ? `市值≥${capB}B` : `cap≥${capB}B`);
      }
      return bits.length > 0 ? bits.join(' · ') : null;
    }
    case 'search_company_ticker':
      return typeof args.q === 'string' ? args.q : null;
    case 'manage_portfolio':
      if (action === 'create' && name) {
        return locale === 'zh' ? `创建 · ${name}` : `Create · ${name}`;
      }
      if (action && portfolioId) return `${action} · ${portfolioId}`;
      return action ?? name;
    case 'add_portfolio_holdings':
    case 'add_portfolio_holding':
      if (holdings?.length) {
        const tickers = holdings
          .map((row) => (typeof row === 'object' && row && 'ticker' in row ? String(row.ticker) : ''))
          .filter(Boolean);
        return locale === 'zh'
          ? `${holdings.length} 只 · ${previewTickers(tickers)}`
          : `${holdings.length} holdings · ${previewTickers(tickers)}`;
      }
      return portfolioId ?? null;
    case 'auto_allocate_portfolio': {
      const bits = [strategy, market].filter(Boolean);
      return bits.length > 0 ? bits.join(' · ') : portfolioId;
    }
    case 'get_portfolio_analysis':
      return portfolioId;
    default:
      if (ticker && market) return `${ticker} · ${market}`;
      if (market) return market;
      return null;
  }
}

export function formatToolResultData(
  data: AgentToolResultData | null | undefined,
  locale: 'zh' | 'en',
): string | null {
  if (!data) return null;
  const parts: string[] = [];
  if (data.portfolio_id) {
    parts.push(`${locale === 'zh' ? '组合' : 'Portfolio'} ${data.portfolio_id.slice(0, 12)}`);
  }
  if (data.name) {
    parts.push(data.name);
  }
  if (data.holdings_by_market && Object.keys(data.holdings_by_market).length > 0) {
    parts.push(formatMarketCounts(data.holdings_by_market, locale));
  } else if (typeof data.holdings_count === 'number') {
    parts.push(locale === 'zh' ? `共 ${data.holdings_count} 只` : `${data.holdings_count} holdings`);
  }
  if (data.tickers && data.tickers.length > 0) {
    parts.push(previewTickers(data.tickers, 8));
  }
  return parts.length > 0 ? parts.join(' · ') : null;
}
