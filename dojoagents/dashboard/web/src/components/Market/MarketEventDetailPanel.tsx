import { memo, useMemo, type CSSProperties } from 'react';
import type { MarketCode } from '../../types/market';
import type { MarketDynamicsEvent, MarketDynamicsSectorImpact } from '../../types/marketDynamics';
import { useTranslation } from '../../hooks/useTranslation';
import { DEFAULT_MARKET_ORDER } from '../../navigation/marketColumnOrder';
import {
  directionClass,
  directionColor,
  directionLabelKey,
} from '../../utils/marketDynamicsFormat';
import { MARKET_CODE, MARKET_FLAG_IMAGE } from '../../utils/marketDisplay';
import './MarketEventTimeline.css';

interface MarketEventDetailPanelProps {
  event: MarketDynamicsEvent;
  impacts: MarketDynamicsSectorImpact[];
  marketOrder?: MarketCode[];
  onSectorJump?: (impact: MarketDynamicsSectorImpact) => void;
}

function toMarketCode(raw: string): MarketCode | null {
  const key = String(raw || '')
    .trim()
    .toLowerCase();
  if (key === 'us' || key === 'cn' || key === 'hk') return key;
  if (key === 'sh' || key === 'sz' || key === 'a' || key === 'ashare') return 'cn';
  return null;
}

function sortMarketsByPageOrder(markets: string[], marketOrder: MarketCode[]): MarketCode[] {
  const rank = new Map(marketOrder.map((code, index) => [code, index]));
  const seen = new Set<MarketCode>();
  const codes: MarketCode[] = [];
  for (const raw of markets) {
    const code = toMarketCode(raw);
    if (!code || seen.has(code)) continue;
    seen.add(code);
    codes.push(code);
  }
  return codes.sort((a, b) => (rank.get(a) ?? 99) - (rank.get(b) ?? 99));
}

function ImpactMarkets({
  markets,
  marketOrder,
}: {
  markets: string[];
  marketOrder: MarketCode[];
}) {
  const ordered = useMemo(
    () => sortMarketsByPageOrder(markets, marketOrder),
    [markets, marketOrder],
  );
  if (ordered.length === 0) return null;
  return (
    <span className="ed-pill__markets">
      {ordered.map((code) => (
        <span key={code} className={`ed-pill__market ed-pill__market--${code}`}>
          <img
            className="ed-pill__market-flag"
            src={MARKET_FLAG_IMAGE[code]}
            alt=""
            aria-hidden
          />
          <span className="ed-pill__market-code">{MARKET_CODE[code]}</span>
        </span>
      ))}
    </span>
  );
}

function ImpactPill({
  impact,
  marketOrder,
  onSectorJump,
}: {
  impact: MarketDynamicsSectorImpact;
  marketOrder: MarketCode[];
  onSectorJump?: (impact: MarketDynamicsSectorImpact) => void;
}) {
  const { t, text } = useTranslation();
  const accent = directionColor(impact.direction);
  const name = text(impact.sector_name);
  const jumpable = Boolean(onSectorJump && name);

  return (
    <span
      className="ed-pill"
      data-connector-pill={impact.sector_id}
      style={{ '--impact-accent': accent } as CSSProperties}
    >
      {jumpable ? (
        <button
          type="button"
          className="ed-pill__name ed-pill__name--link"
          onClick={() => onSectorJump?.(impact)}
          title={t('marketPage.jumpToSector')}
        >
          {name}
        </button>
      ) : (
        <span className="ed-pill__name">{name || '—'}</span>
      )}
      <ImpactMarkets markets={impact.affected_markets ?? []} marketOrder={marketOrder} />
      <span className={`sector-tag sector-tag--xs ${directionClass(impact.direction)}`}>
        {t(directionLabelKey(impact.direction))}
      </span>
    </span>
  );
}

export const MarketEventDetailPanel = memo(function MarketEventDetailPanel({
  event,
  impacts,
  marketOrder = DEFAULT_MARKET_ORDER,
  onSectorJump,
}: MarketEventDetailPanelProps) {
  const { t, text } = useTranslation();
  const content = text(event.event_summary?.content ?? { zh: '', en: '' }) || '—';
  const source = text(event.event_summary?.source ?? { zh: '', en: '' }) || '';

  return (
    <div className="event-detail">
      <div className="ed-layout ed-layout--band">
        {impacts.length > 0 ? (
          <header className="ed-hd ed-hd--band" aria-label={t('marketPage.eventSectorImpacts')}>
            <div className="ed-band__scroll">
              <div className="ed-band__chips">
                {impacts.map((impact) => (
                  <ImpactPill
                    key={impact.sector_id}
                    impact={impact}
                    marketOrder={marketOrder}
                    onSectorJump={onSectorJump}
                  />
                ))}
              </div>
            </div>
          </header>
        ) : null}
        <div className="ed-body">
          <p className="ed-text">{content}</p>
          {source ? (
            <p className="ed-source">
              <span className="ed-source__prefix">{t('marketPage.eventSourceShort')} · </span>
              {source}
            </p>
          ) : null}
        </div>
      </div>
    </div>
  );
});
