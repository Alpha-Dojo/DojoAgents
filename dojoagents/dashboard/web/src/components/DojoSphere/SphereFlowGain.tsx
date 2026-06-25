import { useTranslation } from '../../hooks/useTranslation';
import type { SphereFlowGauge } from '../../mocks/dojoSphereMock';

interface SphereFlowGainProps {
  gauges: SphereFlowGauge[];
}

const MARKET_LABEL: Record<SphereFlowGauge['market'], string> = {
  us: 'US',
  cn: 'CN',
  hk: 'HK',
};

export function SphereFlowGain({ gauges }: SphereFlowGainProps) {
  const { t } = useTranslation();

  return (
    <article className="sphere-card sphere-flow-gain">
      <h3 className="sphere-card__title sphere-card__title--compact">{t('sphere.flowGain')}</h3>
      <div className="sphere-flow-gain__grid">
        {gauges.map((gauge) => {
          const positive = gauge.changePercent >= 0;
          const pct = Math.min(Math.abs(gauge.changePercent) * 18, 100);
          return (
            <div key={gauge.market} className="sphere-flow-gain__item">
              <div
                className={`sphere-flow-gain__gauge ${positive ? 'sphere-flow-gain__gauge--up' : 'sphere-flow-gain__gauge--down'}`}
                style={{ ['--pct' as string]: `${pct}%` }}
              >
                <span className="sphere-flow-gain__market">{MARKET_LABEL[gauge.market]}</span>
                <span className="sphere-flow-gain__value">
                  {positive ? '+' : ''}
                  {gauge.changePercent.toFixed(2)}%
                </span>
              </div>
              <span className="sphere-flow-gain__inflow">{gauge.inflowLabel}</span>
            </div>
          );
        })}
      </div>
    </article>
  );
}
