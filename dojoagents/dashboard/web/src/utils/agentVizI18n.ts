import { displayLocaleText } from '../i18n/locale';
import type { AppLocale } from '../i18n/locale';
import type {
  AgentVizBlock,
  AgentVizKpiItem,
  AgentVizMarketKpiGroup,
  AgentVizTableColumn,
} from '../types/agentViz';

type TranslateFn = (key: string, vars?: Record<string, string | number>) => string;

const COL_LABEL_KEYS: Record<string, string> = {
  ticker: 'agentViz.col.ticker',
  name_zh: 'agentViz.col.name',
  name: 'agentViz.col.name',
  market_cap: 'agentViz.col.marketCap',
  change_percent: 'agentViz.col.todayPnl',
  total_return_pct: 'agentViz.col.totalPnl',
  pe: 'agentViz.col.pe',
  weight: 'agentViz.col.weight',
  level1_id: 'agentViz.col.l1',
  level2_id: 'agentViz.col.l2',
  level3_id: 'agentViz.col.l3',
  kind: 'agentViz.col.kind',
  net_value_usd: 'agentViz.col.netValue',
  today_change: 'agentViz.col.today',
};

const KPI_LABEL_KEYS: Record<string, string> = {
  return: 'agentViz.kpi.return',
  sharpe: 'agentViz.kpi.sharpe',
  mdd: 'agentViz.kpi.maxDrawdown',
  netValue: 'agentViz.kpi.netValue',
  market_cap: 'agentViz.kpi.marketCap',
  weighted_pe: 'agentViz.kpi.weightedPe',
  listed_count: 'agentViz.kpi.listedCount',
  benchmark: 'agentViz.kpi.benchmark',
};

const KPI_LABEL_ALIASES: Record<string, string> = {
  累计收益: 'return',
  夏普: 'sharpe',
  最大回撤: 'mdd',
  净值: 'netValue',
  'Cumulative return': 'return',
  Sharpe: 'sharpe',
  'Max drawdown': 'mdd',
  'Net value': 'netValue',
  'Total market cap': 'market_cap',
  'Weighted PE': 'weighted_pe',
  Listed: 'listed_count',
};

const BAR_SERIES_KEYS: Record<string, string> = {
  revenue: 'agentViz.series.revenue',
  profit: 'agentViz.series.netProfit',
  Revenue: 'agentViz.series.revenue',
  'Net profit': 'agentViz.series.netProfit',
};

const INCOME_DIM_KEYS: Record<string, string> = {
  product: 'agentViz.dim.product',
  industry: 'agentViz.dim.industry',
  region: 'agentViz.dim.region',
};

const PORTFOLIO_TITLE_KEYS: Record<string, string> = {
  持仓权重: 'agentViz.holdingsWeight',
  持仓明细: 'agentViz.holdingsDetail',
  净值曲线: 'agentViz.navCurve',
  'Holdings weight': 'agentViz.holdingsWeight',
  Holdings: 'agentViz.holdingsDetail',
  'Portfolio NAV': 'agentViz.navCurve',
};

function columnLabelKey(col: AgentVizTableColumn, sourceTool?: string): string | undefined {
  if (sourceTool === 'list_or_search_portfolios' && col.key === 'name') {
    return 'agentViz.col.portfolio';
  }
  if (sourceTool === 'get_taxonomy_tree' && col.key === 'name_zh') {
    return 'agentViz.col.sector';
  }
  return COL_LABEL_KEYS[col.key];
}

function localizeColumn(
  col: AgentVizTableColumn,
  t: TranslateFn,
  sourceTool?: string,
): AgentVizTableColumn {
  const key = columnLabelKey(col, sourceTool);
  if (!key) return col;
  return { ...col, label: t(key) };
}

function localizeKpiItem(item: AgentVizKpiItem, t: TranslateFn): AgentVizKpiItem {
  const aliasKey = item.key ?? KPI_LABEL_ALIASES[item.label];
  const labelKey = aliasKey ? KPI_LABEL_KEYS[aliasKey] : undefined;
  let label = labelKey ? t(labelKey) : item.label;
  if (item.key === 'benchmark' && item.label && !labelKey) {
    label = item.label;
  }
  let meta = item.meta;
  if (meta) {
    const peMatch = /^PE\s+([\d.]+)$/i.exec(meta);
    if (peMatch) {
      meta = t('agentViz.kpi.peMeta', { value: peMatch[1] });
    } else {
      const stocksMatch = /^(\d+)\s+stocks$/i.exec(meta);
      if (stocksMatch) {
        meta = t('agentViz.kpi.stocks', { count: stocksMatch[1] });
      }
    }
  }
  return {
    ...item,
    label,
    meta,
  };
}

function localizeSubtitle(subtitle: string, t: TranslateFn): string {
  if (subtitle === 'total') return t('agentViz.totalReturn');

  const windowMatch = /^(\d+)D window$/i.exec(subtitle);
  if (windowMatch) return t('agentViz.daysWindow', { days: windowMatch[1] });

  const daysMatch = /^(\d+)D$/i.exec(subtitle);
  if (daysMatch) return t('agentViz.daysShort', { days: daysMatch[1] });

  const sectorsMatch = /^(\d+)\s+sectors$/i.exec(subtitle);
  if (sectorsMatch) return t('agentViz.sectorCount', { count: sectorsMatch[1] });

  const matchesMatch = /^(.+) · (\d+) matches$/i.exec(subtitle);
  if (matchesMatch) {
    const base = localizeSubtitle(matchesMatch[1], t);
    return `${base} · ${t('agentViz.screenMatches', { count: matchesMatch[2] })}`;
  }

  return subtitle;
}

function localizeIncomeDimension(dimension: string, t: TranslateFn): string {
  const key = INCOME_DIM_KEYS[dimension.toLowerCase()];
  return key ? t(key) : dimension;
}

function resolveBlockTitle(block: AgentVizBlock, t: TranslateFn, locale: AppLocale): string {
  const tool = block.source_tool ?? '';
  const title = block.title;

  if (tool === 'get_portfolio_analysis') {
    const portfolioKey = PORTFOLIO_TITLE_KEYS[title];
    if (portfolioKey) return t(portfolioKey);
    return title;
  }

  if (tool === 'get_market_overview' && block.kind === 'sparkline') {
    const nameZh = block.payload.name_zh as string | undefined;
    const nameEn = block.payload.name_en as string | undefined;
    if (nameZh || nameEn) {
      return displayLocaleText({ zh: nameZh ?? '', en: nameEn ?? '' }, locale);
    }
  }

  if (tool === 'get_ticker_realtime_quote') {
    return title;
  }

  const financialsMatch = /^Financials · (.+)$/i.exec(title);
  if (financialsMatch) return t('agentViz.financials', { ticker: financialsMatch[1] });

  const incomeMatch = /^Income · (.+)$/i.exec(title);
  if (incomeMatch) {
    const dimension = (block.payload.dimension as string | undefined) ?? incomeMatch[1];
    return t('agentViz.income', { dimension: localizeIncomeDimension(dimension, t) });
  }

  const priceMatch = /^Price · (.+)$/i.exec(title);
  if (priceMatch) return t('agentViz.price', { ticker: priceMatch[1] });

  const newsMatch = /^News & events · (.+)$/i.exec(title);
  if (newsMatch) return t('agentViz.newsEvents', { ticker: newsMatch[1] });

  const toolTitleKeys: Record<string, string | ((kind: string) => string | null)> = {
    search_company_ticker: 'agentViz.tickerSearch',
    get_taxonomy_tree: 'agentViz.sectorTaxonomy',
    get_market_overview: 'agentViz.marketOverview',
    get_sector_movers: 'agentViz.sectorMovers',
    screen_market_stocks: 'agentViz.marketScreen',
    get_sector_analysis: (kind) =>
      kind === 'line' ? 'agentViz.sectorNav' : 'agentViz.sectorPerformance',
    filter_sector_constituents: 'agentViz.sectorConstituents',
    list_or_search_portfolios: 'agentViz.portfolios',
  };

  const mapped = toolTitleKeys[tool];
  if (typeof mapped === 'function') {
    const key = mapped(block.kind);
    return key ? t(key) : title;
  }
  if (typeof mapped === 'string') {
    return t(mapped);
  }

  return title;
}

function localizePayload(
  block: AgentVizBlock,
  payload: Record<string, unknown>,
  t: TranslateFn,
): Record<string, unknown> {
  const next: Record<string, unknown> = { ...payload };

  if (Array.isArray(payload.columns)) {
    next.columns = (payload.columns as AgentVizTableColumn[]).map((col) =>
      localizeColumn(col, t, block.source_tool),
    );
  }

  if (Array.isArray(payload.items)) {
    next.items = (payload.items as AgentVizKpiItem[]).map((item) => localizeKpiItem(item, t));
  }

  if (Array.isArray(payload.markets)) {
    next.markets = (payload.markets as AgentVizMarketKpiGroup[]).map((group) => ({
      ...group,
      items: group.items.map((item) => localizeKpiItem(item, t)),
    }));
  }

  if (Array.isArray(payload.series) && block.kind === 'bar') {
    next.series = (
      payload.series as { name?: string; label: string; values: (number | null)[] }[]
    ).map((series) => {
      const key = series.name ? BAR_SERIES_KEYS[series.name] : BAR_SERIES_KEYS[series.label];
      return key ? { ...series, label: t(key) } : series;
    });
  }

  return next;
}

export function localizeAgentVizBlock(
  block: AgentVizBlock,
  t: TranslateFn,
  locale: AppLocale,
): AgentVizBlock {
  return {
    ...block,
    title: resolveBlockTitle(block, t, locale),
    subtitle: block.subtitle ? localizeSubtitle(String(block.subtitle), t) : block.subtitle,
    payload: localizePayload(block, block.payload, t),
  };
}

export function localizeAgentVizBlocks(
  blocks: AgentVizBlock[],
  t: TranslateFn,
  locale: AppLocale,
): AgentVizBlock[] {
  return blocks.map((block) => localizeAgentVizBlock(block, t, locale));
}
