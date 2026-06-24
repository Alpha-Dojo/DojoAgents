const TOOL_LABELS: Record<string, { zh: string; en: string }> = {
  search_company_ticker: { zh: '搜索股票代码', en: 'Search ticker' },
  get_taxonomy_tree: { zh: '加载行业分类', en: 'Load sector taxonomy' },
  get_market_overview: { zh: '获取市场概览', en: 'Market overview' },
  get_sector_movers: { zh: '获取板块涨跌', en: 'Sector movers' },
  screen_market_stocks: { zh: '全市场选股', en: 'Market screen' },
  get_sector_analysis: { zh: '分析行业板块', en: 'Sector analysis' },
  filter_sector_constituents: { zh: '筛选成分股', en: 'Sector constituents' },
  get_ticker_realtime_quote: { zh: '获取实时报价', en: 'Realtime quote' },
  get_ticker_financials: { zh: '获取财务数据', en: 'Financials' },
  get_ticker_news_and_events: { zh: '获取新闻公告', en: 'News & events' },
  get_ticker_price_trends: { zh: '获取价格走势', en: 'Price trends' },
  list_or_search_portfolios: { zh: '查询投资组合', en: 'List portfolios' },
  get_portfolio_analysis: { zh: '分析投资组合', en: 'Portfolio analysis' },
  manage_portfolio: { zh: '管理投资组合', en: 'Manage portfolio' },
  add_portfolio_holding: { zh: '添加持仓', en: 'Add holding' },
  add_portfolio_holdings: { zh: '批量添加持仓', en: 'Add holdings' },
  auto_allocate_portfolio: { zh: '自动分配权重', en: 'Auto allocate' },
};

export function agentToolLabel(tool: string, locale: 'zh' | 'en'): string {
  const entry = TOOL_LABELS[tool];
  if (entry) return locale === 'zh' ? entry.zh : entry.en;
  return tool;
}
