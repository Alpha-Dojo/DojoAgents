import { useMemo, useState } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import type { BenchmarkCard, MarketCode, MarketStats } from '../../types/dojoMesh';
import { formatMarketCap, formatPe, formatPlainCount } from '../../utils/marketStats';
import type { MarketBrandDragProps } from './DraggableMarketColumn';
import { Sparkline } from './Sparkline';

interface MarketHeroCardProps {
  flagSrc: string;
  label: string;
  stats: MarketStats;
  benchmarks: BenchmarkCard[];
  defaultSymbol?: string;
  chartWindowStart?: string;
  chartWindowEnd?: string;
  linkedHoverDate?: string | null;
  onLinkedHoverDateChange?: (date: string | null) => void;
  brandDrag?: MarketBrandDragProps;
}

function capLabelKey(market: MarketCode): 'marketCapUs' | 'marketCapSh' | 'marketCapHk' {
  if (market === 'us') return 'marketCapUs';
  if (market === 'cn') return 'marketCapSh';
  return 'marketCapHk';
}

export function MarketHeroCard({
  flagSrc,
  label,
  stats,
  benchmarks,
  defaultSymbol,
  chartWindowStart,
  chartWindowEnd,
  linkedHoverDate,
  onLinkedHoverDateChange,
  brandDrag,
}: MarketHeroCardProps) {
  const { t } = useTranslation();
  const initialSymbol = defaultSymbol ?? benchmarks[0]?.symbol ?? '';
  const [symbol, setSymbol] = useState(initialSymbol);

  const statItems = useMemo(
    () =>
      [
        { key: 'listed', label: t('market.listedCount'), format: (s: MarketStats) => formatPlainCount(s.listed_count) },
        { key: 'cap', label: t(`market.${capLabelKey(stats.market)}`), format: (s: MarketStats) => formatMarketCap(s.total_market_cap) },
        { key: 'wpe', label: t('market.weightedPe'), format: (s: MarketStats) => formatPe(s.weighted_pe) },
        { key: 'sample', label: t('market.peSample'), format: (s: MarketStats) => formatPlainCount(s.pe_sample_count) },
      ] as const,
    [stats.market, t],
  );

  const benchmark = useMemo(
    () => benchmarks.find((b) => b.symbol === symbol) ?? benchmarks[0],
    [benchmarks, symbol],
  );

  const chartId = `${stats.market}-hero`.replace(/[^a-zA-Z0-9-]/g, '');

  return (
    <article className="market-hero">
      <div className="market-hero__meta">
        <div
          className={`market-hero__brand${brandDrag ? ' market-hero__brand--draggable' : ''}`}
          {...brandDrag}
        >
          <img className="market-hero__flag" src={flagSrc} alt="" aria-hidden />
          <span className="market-hero__label">{label}</span>
        </div>
        <div className="market-hero__stats" role="group" aria-label={t('market.statsLabel')}>
          {statItems.map(({ key, label: statLabel, format }) => (
            <div key={key} className="market-hero__stat">
              <span className="market-hero__stat-label">{statLabel}</span>
              <span className="market-hero__stat-value">{format(stats)}</span>
            </div>
          ))}
        </div>
      </div>

      {benchmark ? (
        <Sparkline
          kline={benchmark.kline}
          positive={benchmark.change_percent >= 0}
          id={chartId}
          currentPrice={benchmark.price}
          changePercent={benchmark.change_percent}
          benchmarks={benchmarks}
          symbol={benchmark.symbol}
          onSymbolChange={setSymbol}
          windowStart={chartWindowStart}
          windowEnd={chartWindowEnd}
          linkedHoverDate={linkedHoverDate}
          onLinkedHoverDateChange={onLinkedHoverDateChange}
        />
      ) : (
        <div className="market-hero__chart-empty" aria-label={t('market.noBenchmark')}>
          <p className="market-hero__chart-empty-text">{t('market.noBenchmark')}</p>
        </div>
      )}
    </article>
  );
}
