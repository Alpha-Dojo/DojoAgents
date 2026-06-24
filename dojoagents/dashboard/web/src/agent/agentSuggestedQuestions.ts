import type { AppTab } from '../navigation/appTab';
import type { AppLocale } from '../i18n/locale';

const SUGGESTED_QUESTIONS: Record<AppTab, Record<AppLocale, string[]>> = {
  mesh: {
    zh: [
      '港股今日市场概览怎样？us/cn/hk 近 5 日表现对比如何？',
      '最近 5 日领涨和领跌的行业板块有哪些？',
      '美股市值超 100 亿、自 2025-01-01 以来涨超 300% 的股票有哪些？',
      '对比 us、cn、hk 三市场的总市值与加权 PE',
      'A 股半导体板块近期涨跌表现如何？',
    ],
    en: [
      'How is the HK market today? Compare us/cn/hk over the last 5 sessions.',
      'Which sectors led gains and losses over the last 5 sessions?',
      'US stocks with market cap above $10B and total return above 300% since 2025-01-01?',
      'Compare total market cap and weighted PE across us, cn, and hk.',
      'How has the A-share semiconductor sector performed recently?',
    ],
  },
  sphere: {
    zh: [
      '帮我列出半导体相关的三级行业分类',
      '港股综合性商业银行板块成分股有哪些？筛 PE 较低的',
      '近期领跌的行业板块有哪些？（总涨跌幅维度 days:0）',
      '对比金融与科技板块的行业净值表现',
      '商业航天相关板块在美股的近期表现',
    ],
    en: [
      'List L3 sectors related to semiconductors.',
      'HK diversified commercial bank constituents with lower PE.',
      'Which sectors led losses recently? (total return, days:0)',
      'Compare financials vs technology sector NAV performance.',
      'How have commercial aerospace sectors performed in the US?',
    ],
  },
  core: {
    zh: [
      '英伟达最新财务数据和估值水平如何？',
      '腾讯近 90 日价格走势与最大回撤是多少？',
      '建设银行最新新闻与公告有哪些？',
      '美光科技的收入结构 breakdown',
      '搜索港股「招商银行」并查看实时报价',
    ],
    en: [
      'Latest financials and valuation for NVIDIA.',
      'Tencent price trends over 90 sessions and max drawdown.',
      'Latest news and events for China Construction Bank.',
      'Micron income breakdown by segment.',
      'Search HK ticker for China Merchants Bank and show realtime quote.',
    ],
  },
  folio: {
    zh: [
      '在 us/cn/hk 各选 6 只市值超 100 亿、累计涨超 300% 的股票，等权建仓到新组合',
      '分析「明星股」组合的夏普比率、最大回撤和净值曲线',
      '「半导体与存储」组合的行业集中度与风险敞口如何？',
      '对美股持仓执行平等权重配平',
      '列出所有投资组合及各市场持仓数量',
    ],
    en: [
      'Pick 6 stocks per market (us/cn/hk) with cap >10B and total return >300%, equal-weight new portfolio.',
      'Analyze Sharpe, max drawdown, and NAV for the Star Stocks portfolio.',
      'Sector concentration and risk exposure for Semiconductors & Storage.',
      'Equal-weight rebalance US holdings.',
      'List all portfolios and holdings count by market.',
    ],
  },
};

export function suggestedQuestionsForTab(tab: AppTab, locale: AppLocale): string[] {
  return SUGGESTED_QUESTIONS[tab][locale] ?? SUGGESTED_QUESTIONS[tab].zh;
}
