const TOOL_LABELS: Record<string, { zh: string; en: string }> = {
  search_company_ticker: { zh: '搜索股票代码', en: 'Search ticker' },
  get_taxonomy_tree: { zh: '加载行业分类', en: 'Load sector taxonomy' },
  search_sector_taxonomy: { zh: '搜索行业板块', en: 'Search sectors' },
  get_market_overview: { zh: '获取市场概览', en: 'Market overview' },
  get_sector_movers: { zh: '获取板块涨跌', en: 'Sector movers' },
  screen_market_stocks: { zh: '全市场选股', en: 'Market screen' },
  get_sector_analysis: { zh: '分析行业板块', en: 'Sector analysis' },
  filter_sector_constituents: { zh: '筛选成分股', en: 'Sector constituents' },
  get_ticker_realtime_quote: { zh: '获取实时报价', en: 'Realtime quote' },
  get_ticker_financials: { zh: '获取财务数据', en: 'Financials' },
  get_ticker_news_and_events: { zh: '获取新闻公告', en: 'News & events' },
  get_ticker_price_trends: { zh: '获取价格走势', en: 'Price trends' },
  'dojo.sdk.benchmark.kline': { zh: '获取指数K线', en: 'Benchmark kline' },
  'dojo.sdk.stock.current_quote': { zh: '获取股票报价', en: 'Stock quote' },
  'dojo.sdk.stock.kline': { zh: '获取股票K线', en: 'Stock kline' },
  'dojo.sdk.stock.ystock_info': { zh: '获取股票资料', en: 'Stock profile' },
  'dojo.sdk.stock.news': { zh: '获取股票新闻', en: 'Stock news' },
  'dojo.sdk.stock.event_remind': { zh: '获取事件提醒', en: 'Event reminders' },
  'dojo.sdk.stock.main_income': { zh: '获取主营收入', en: 'Main income' },
  'dojo.sdk.stock.fin_indicators': { zh: '获取财务指标', en: 'Financial indicators' },
  'dojo.sdk.forex.kline': { zh: '获取外汇K线', en: 'Forex kline' },
  web_search: { zh: '搜索资料', en: 'Web search' },
  web_extract: { zh: '提取网页', en: 'Web extract' },
  agent_viz_build: { zh: '生成可视化', en: 'Build visualization' },
  list_or_search_portfolios: { zh: '查询投资组合', en: 'List portfolios' },
  get_portfolio_analysis: { zh: '分析投资组合', en: 'Portfolio analysis' },
  manage_portfolio: { zh: '管理投资组合', en: 'Manage portfolio' },
  add_portfolio_holding: { zh: '添加持仓', en: 'Add holding' },
  add_portfolio_holdings: { zh: '批量添加持仓', en: 'Add holdings' },
  portfolio_write_add_holding: { zh: '添加候选股', en: 'Add candidate' },
  portfolio_write_add_holdings: { zh: '批量添加候选股', en: 'Add candidates' },
  portfolio_eval_submit: { zh: '提交任务验收', en: 'Submit eval' },
  auto_allocate_portfolio: { zh: '自动分配权重', en: 'Auto allocate' },
};

export function agentToolLabel(tool: string, locale: 'zh' | 'en'): string {
  const entry = TOOL_LABELS[tool];
  if (entry) return locale === 'zh' ? entry.zh : entry.en;
  return tool;
}
