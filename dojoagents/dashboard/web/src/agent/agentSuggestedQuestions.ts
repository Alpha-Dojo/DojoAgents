import { readPersistedSectorSelection } from '../cache/sectorViewState';
import type { AppLocale } from '../i18n/locale';
import { readEntityTickerContext, resolveEntityTickerContext } from '../navigation/entityContext';
import { resolveActiveFolioPortfolioName } from '../navigation/folioContext';
import type { AppTab } from '../navigation/appTab';
import type { BilingualLabel, SectorTaxonomyDocument } from '../types/sectorTaxonomy';
import { findSectorPathByIds, getSectorDefaultSelection } from '../utils/sectorTaxonomy';

export interface SuggestedQuestionContext {
  sphereL2: string;
  sphereL3: string;
  coreCompanyName: string;
  portfolioName: string;
}

const SUGGESTED_QUESTION_TEMPLATES: Record<AppTab, Record<AppLocale, string[]>> = {
  market: {
    zh: [
      '中美港三地大盘，目前哪边的估值最便宜？',
      '今天全球市场有何异动？哪个板块在带头砸盘？',
      '过去一周，全市场资金都在疯狂抢筹哪些板块？',
      '美股大涨的板块中，A股有哪些同概念板块可以跟涨？',
      '标普500当前溢价较高，现在还有追高的空间吗？',
    ],
    en: [
      'Among US, CN, and HK, which market looks cheapest on valuation today?',
      'What moved globally today? Which sectors are leading the selloff?',
      'Over the past week, which sectors saw the strongest fund inflows across all markets?',
      'Among US sectors that rallied, which A-share concept sectors could follow?',
      'The S&P 500 looks richly valued—is there still room to chase higher?',
    ],
  },
  sector: {
    zh: [
      '对比中美港三地，{L3}板块现在哪边性价比最高？',
      '{L2}产业链中，最近哪个细分赛道在领涨？',
      '帮我在美股{L3}板块中，筛选出市值大且低市盈率的龙头股。',
      '帮我在全市场{L3}板块中，筛选出市值大且年涨跌幅翻倍的成分股。',
      '对比一下全球市场「金融」与「科技」板块近期的净值表现。',
    ],
    en: [
      'Across US, CN, and HK, where does {L3} offer the best value now?',
      'Within {L2}, which sub-sector has been leading gains recently?',
      'Screen US {L3} for large-cap leaders with low P/E.',
      'Screen global {L3} for large-cap names with 100%+ trailing return.',
      'Compare recent NAV performance of global Financials vs Technology.',
    ],
  },
  entity: {
    zh: [
      '{ticker} 当前的估值算便宜还是贵？',
      '{ticker} 目前最赚钱的核心业务是哪个？',
      '{ticker} 作为「高股息」防守配置，现在买入稳当吗？',
      '{ticker} 的股价处于历史什么水位？可以建仓了吗？',
      '帮我把 {ticker} 的核心收入，按地区和产品维度拆解一下。',
    ],
    en: [
      'Is {ticker} cheap or expensive on valuation today?',
      'What is {ticker}’s most profitable core business right now?',
      'Is {ticker} a stable high-dividend defensive buy now?',
      'Where is {ticker} trading vs its historical range—is it a good entry?',
      'Break down {ticker}’s core revenue by region and product line.',
    ],
  },
  folio: {
    zh: [
      '当前 {portfolio} 最大的风险是什么？',
      '如果美联储降息，对 {portfolio} 影响如何？',
      '帮我挑 5 只低估值的美股高息股，并创建投资组合',
      '有哪些低相关性资产可以分散 {portfolio} 的投资风险？',
      '半导体行业近期是利多还是利空，{portfolio} 还需要调整仓位吗？',
    ],
    en: [
      'What is the biggest risk in {portfolio} right now?',
      'If the Fed cuts rates, how would that affect {portfolio}?',
      'Pick 5 undervalued US high-dividend stocks and create a portfolio.',
      'What low-correlation assets could diversify risk in {portfolio}?',
      'Are semiconductors bullish or bearish lately—does {portfolio} need position adjustments?',
    ],
  },
};

function localizedLabel(label: BilingualLabel, locale: AppLocale): string {
  return locale === 'zh' ? label.zh || label.en : label.en || label.zh;
}

function applySuggestedQuestionTemplate(template: string, context: SuggestedQuestionContext): string {
  return template
    .replaceAll('{L3}', context.sphereL3)
    .replaceAll('{L2}', context.sphereL2)
    .replaceAll('{ticker}', context.coreCompanyName)
    .replaceAll('{portfolio}', context.portfolioName);
}

export function resolveSuggestedQuestionContext(
  locale: AppLocale,
  taxonomy: SectorTaxonomyDocument | null,
): SuggestedQuestionContext {
  const core = readEntityTickerContext() ?? resolveEntityTickerContext();
  const coreCompanyName =
    locale === 'zh'
      ? core.name_zh || core.name_en || core.ticker
      : core.name_en || core.name_zh || core.ticker;

  const fallbackL2 = locale === 'zh' ? '当前产业链' : 'this industry chain';
  const fallbackL3 = locale === 'zh' ? '当前板块' : 'this sector';

  const portfolioName = resolveActiveFolioPortfolioName(locale);

  if (!taxonomy) {
    return { sphereL2: fallbackL2, sphereL3: fallbackL3, coreCompanyName, portfolioName };
  }

  const selection = readPersistedSectorSelection() ?? getSectorDefaultSelection(taxonomy);
  const path = findSectorPathByIds(taxonomy, selection);
  if (!path) {
    return { sphereL2: fallbackL2, sphereL3: fallbackL3, coreCompanyName, portfolioName };
  }

  return {
    sphereL2: localizedLabel(path.level2.name, locale),
    sphereL3: localizedLabel(path.level3.name, locale),
    coreCompanyName,
    portfolioName,
  };
}

export function suggestedQuestionsForTab(
  tab: AppTab,
  locale: AppLocale,
  context?: SuggestedQuestionContext,
): string[] {
  const templates = SUGGESTED_QUESTION_TEMPLATES[tab][locale] ?? SUGGESTED_QUESTION_TEMPLATES[tab].zh;
  if (!context) {
    return templates;
  }
  return templates.map((template) => applySuggestedQuestionTemplate(template, context));
}
