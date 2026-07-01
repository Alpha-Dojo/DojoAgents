export interface AgentToolResultData {
  portfolio_id?: string;
  name?: string;
  holdings_count?: number;
  holdings_by_market?: Record<string, number>;
  tickers?: string[];
}

function countCodeLines(code: string): number {
  if (!code) return 0;
  return code.replace(/\n+$/, '').split('\n').length;
}

export function getExecuteCodeSource(
  tool: string,
  args: Record<string, unknown> | undefined,
): string | null {
  if (tool !== 'execute_code' || !args) return null;
  const code = typeof args.code === 'string' ? args.code : null;
  if (!code || !code.trim()) return null;
  return code;
}

export function getExecuteCodeResultContent(
  tool: string,
  content: string | null | undefined,
): string | null {
  if (tool !== 'execute_code') return null;
  if (typeof content !== 'string' || !content.trim()) return null;
  return content;
}

function previewValues(values: string[], limit = 4): string {
  const items = values.map((value) => value.trim()).filter(Boolean);
  if (items.length === 0) return '';
  const head = items.slice(0, limit).join(', ');
  if (items.length <= limit) return head;
  return `${head} +${items.length - limit}`;
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

function parseSymbolList(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.filter((item): item is string => typeof item === 'string');
  }
  if (typeof value === 'string') {
    return value
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean);
  }
  return [];
}

export function formatToolArguments(
  tool: string,
  args: Record<string, unknown> | undefined,
  locale: 'zh' | 'en',
): string | null {
  if (!args || Object.keys(args).length === 0) return null;

  const ticker = typeof args.ticker === 'string' ? args.ticker : null;
  const tickers = parseSymbolList(args.tickers);
  const market = typeof args.market === 'string' ? args.market.toUpperCase() : null;
  const symbol = typeof args.symbol === 'string' ? args.symbol : null;
  const symbols = parseSymbolList(args.symbols);
  const interval = typeof args.kline_t === 'string' ? args.kline_t.toUpperCase() : null;
  const action = typeof args.action === 'string' ? args.action : null;
  const name = typeof args.name === 'string' ? args.name : null;
  const query =
    typeof args.q === 'string'
      ? args.q
      : typeof args.query === 'string'
        ? args.query
        : null;
  const url = typeof args.url === 'string' ? args.url : null;
  const portfolioId =
    typeof args.portfolio_id === 'string' ? args.portfolio_id.slice(0, 12) : null;
  const strategy =
    typeof args.allocation_strategy === 'string' ? args.allocation_strategy : null;
  const holdings = Array.isArray(args.holdings) ? args.holdings : null;

  switch (tool) {
    case 'execute_code': {
      const code = getExecuteCodeSource(tool, args);
      if (!code) {
        return locale === 'zh' ? 'Python 脚本' : 'Python script';
      }
      const lineCount = countCodeLines(code);
      return locale === 'zh'
        ? `Python 脚本 · ${lineCount} 行`
        : `Python script · ${lineCount} ${lineCount === 1 ? 'line' : 'lines'}`;
    }
    case 'get_ticker_financials':
      if (tickers.length > 0) {
        const preview = previewTickers(tickers);
        return market ? `${preview} · ${market}` : preview;
      }
      if (ticker && market) return `${ticker} · ${market}`;
      if (ticker) return ticker;
      return null;
    case 'get_ticker_price_trends':
    case 'get_ticker_news_and_events':
      if (ticker && market) return `${ticker} · ${market}`;
      if (ticker) return ticker;
      return null;
    case 'get_ticker_realtime_quote':
      if (tickers.length > 0) {
        const preview = previewTickers(tickers);
        return market ? `${preview} · ${market}` : preview;
      }
      if (ticker && market) return `${ticker} · ${market}`;
      if (ticker) return ticker;
      return null;
    case 'dojo.sdk.benchmark.kline':
    case 'dojo.sdk.stock.kline':
    case 'dojo.sdk.forex.kline': {
      const bits = [symbol, market, interval].filter(Boolean);
      return bits.length > 0 ? bits.join(' · ') : null;
    }
    case 'dojo.sdk.stock.current_quote':
      return symbols.length > 0 ? previewValues(symbols) : null;
    case 'dojo.sdk.stock.ystock_info': {
      const bits = [];
      if (symbols.length > 0) bits.push(previewValues(symbols));
      if (market) bits.push(market);
      return bits.length > 0 ? bits.join(' · ') : null;
    }
    case 'dojo.sdk.stock.news':
    case 'dojo.sdk.stock.event_remind':
    case 'dojo.sdk.stock.main_income':
    case 'dojo.sdk.stock.fin_indicators': {
      const bits = [symbol, market].filter(Boolean);
      if (typeof args.report_type === 'string') bits.push(args.report_type);
      return bits.length > 0 ? bits.join(' · ') : null;
    }
    case 'web_search':
      return query;
    case 'web_extract':
      return url;
    case 'agent_viz_build': {
      const title = typeof args.title === 'string' ? args.title.trim() : null;
      const subtitle = typeof args.subtitle === 'string' ? args.subtitle.trim() : null;
      const mappingHint = typeof args.mapping_hint === 'string' ? args.mapping_hint : null;
      const kind = typeof args.kind === 'string' ? args.kind : null;
      if (title) return title;
      if (subtitle) return subtitle;
      return kind ?? mappingHint;
    }
    case 'get_market_overview':
    case 'get_sector_movers': {
      const bits: string[] = [];
      if (market) bits.push(market);
      if (typeof args.days === 'number') {
        bits.push(`${args.days}${locale === 'zh' ? '日' : 'D'}`);
      }
      return bits.length > 0 ? bits.join(' · ') : null;
    }
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
      return query;
    case 'manage_portfolio':
      if (action === 'create' && name) {
        return locale === 'zh' ? `创建 · ${name}` : `Create · ${name}`;
      }
      if (action && portfolioId) return `${action} · ${portfolioId}`;
      return action ?? name;
    case 'add_portfolio_holdings':
    case 'add_portfolio_holding':
    case 'portfolio_write_add_holdings':
    case 'portfolio_write_add_holding':
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
      if (symbol && interval) return `${symbol} · ${interval}`;
      if (symbols.length > 0 && market) return `${previewValues(symbols)} · ${market}`;
      if (symbols.length > 0) return previewValues(symbols);
      if (query) return query;
      if (url) return url;
      if (symbol && market) return `${symbol} · ${market}`;
      if (ticker && market) return `${ticker} · ${market}`;
      if (market) return market;
      return null;
  }
}

export function formatToolResultData(
  data: (AgentToolResultData & Record<string, unknown>) | Record<string, unknown> | null | undefined,
  locale: 'zh' | 'en',
): string | null {
  if (!data) return null;
  const parts: string[] = [];
  const portfolioId = typeof data.portfolio_id === 'string' ? data.portfolio_id : null;
  const name = typeof data.name === 'string' ? data.name : null;
  const holdingsByMarket =
    data.holdings_by_market && typeof data.holdings_by_market === 'object' && !Array.isArray(data.holdings_by_market)
      ? (data.holdings_by_market as Record<string, number>)
      : null;
  const tickers = Array.isArray(data.tickers) ? data.tickers.filter((item): item is string => typeof item === 'string') : [];
  if (portfolioId) {
    parts.push(`${locale === 'zh' ? '组合' : 'Portfolio'} ${portfolioId.slice(0, 12)}`);
  }
  if (name) {
    parts.push(name);
  }
  if (holdingsByMarket && Object.keys(holdingsByMarket).length > 0) {
    parts.push(formatMarketCounts(holdingsByMarket, locale));
  } else if (typeof data.holdings_count === 'number') {
    parts.push(locale === 'zh' ? `共 ${data.holdings_count} 只` : `${data.holdings_count} holdings`);
  }
  if (tickers.length > 0) {
    parts.push(previewTickers(tickers, 8));
  }
  return parts.length > 0 ? parts.join(' · ') : null;
}
