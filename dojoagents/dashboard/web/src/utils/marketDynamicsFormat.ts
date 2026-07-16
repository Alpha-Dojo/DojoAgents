import type { AppLocale } from '../i18n/locale';
import type {
  EventCategory,
  ImpactDirection,
  SurpriseLevel,
} from '../types/marketDynamics';

const CATEGORY_COLORS: Record<string, string> = {
  geo_military: '#f97316',
  geo_election: '#fb923c',
  geo_sanction: '#ea580c',
  macro_data: '#38bdf8',
  macro_central_bank: '#0ea5e9',
  macro_fx_bond: '#0284c7',
  corporate_earnings: '#a78bfa',
  corporate_ma: '#8b5cf6',
  industry_regulation: '#f472b6',
  industry_supply: '#ec4899',
  industry_price: '#e879f9',
  industry_tech: '#22d3ee',
  market_structure: '#34d399',
  institutional_view: '#94a3b8',
  black_swan: '#f43f5e',
};

export function categoryColor(category: EventCategory): string {
  return CATEGORY_COLORS[category] ?? '#64748b';
}

export function categoryLabelKey(category: EventCategory): string {
  return `eventCategory.${category}`;
}

export function surpriseLabelKey(surprise: SurpriseLevel): string {
  return `eventSurprise.${surprise}`;
}

export function directionLabelKey(direction: ImpactDirection): string {
  return `eventDirection.${direction}`;
}

export function eventMarketLabelKey(market: string): string {
  return `eventMarket.${market}`;
}

export function eventTimeMs(iso: string | null | undefined): number {
  if (!iso) return 0;
  const ms = Date.parse(iso);
  return Number.isNaN(ms) ? 0 : ms;
}

/** Calendar date (YYYY-MM-DD) in the locale timezone used for display. */
export function eventCalendarDate(
  eventTime: string | null | undefined,
  locale: AppLocale = 'zh',
): string | null {
  if (!eventTime) return null;
  const date = new Date(eventTime);
  if (Number.isNaN(date.getTime())) {
    return eventTime.length >= 10 ? eventTime.slice(0, 10) : null;
  }
  const parts = new Intl.DateTimeFormat(locale === 'zh' ? 'zh-CN' : 'en-US', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(date);
  const y = parts.find((p) => p.type === 'year')?.value;
  const m = parts.find((p) => p.type === 'month')?.value;
  const d = parts.find((p) => p.type === 'day')?.value;
  if (!y || !m || !d) return null;
  return `${y}-${m}-${d}`;
}

export function formatEventTime(iso: string, locale: AppLocale): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(locale === 'zh' ? 'zh-CN' : 'en-US', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

export function directionClass(direction: ImpactDirection): string {
  if (direction === 'Positive') return 'direction--positive';
  if (direction === 'Negative') return 'direction--negative';
  if (direction === 'Divergent') return 'direction--divergent';
  return 'direction--neutral';
}

export function surpriseClass(surprise: SurpriseLevel): string {
  if (surprise === 'significant') return 'surprise--significant';
  if (surprise === 'slight') return 'surprise--slight';
  return 'surprise--expected';
}

export function directionColor(direction: ImpactDirection): string {
  if (direction === 'Positive') return '#34d399';
  if (direction === 'Negative') return '#f87171';
  if (direction === 'Divergent') return '#fbbf24';
  return '#94a3b8';
}

export function buildImpactDetailLinks(
  impacts: { sector_id: string; direction: string }[],
): { impactSectorId: string; direction: string }[] {
  return impacts.map((impact) => ({
    impactSectorId: impact.sector_id,
    direction: impact.direction,
  }));
}
