import { useTranslation } from '../../hooks/useTranslation';
import type { CoreAnalystSnapshot } from '../../types/dojoCore';
import { formatCompactNumber } from '../../utils/coreCharts';
import { CoreCard } from './CoreCard';

interface CoreAnalystPanelProps {
  analyst: CoreAnalystSnapshot;
}

export function CoreAnalystPanel({ analyst }: CoreAnalystPanelProps) {
  const { t } = useTranslation();
  const { rating, epsForecast } = analyst;
  const epsMax = Math.max(...epsForecast.map((e) => e.eps), 1);

  return (
    <CoreCard title={t('core.analystTitle')} className="core-card--analyst">
      <div className="core-analyst">
        <section className="core-analyst__section">
          <h4 className="core-analyst__subtitle">{t('core.epsForecastTitle')}</h4>
          <div className="core-analyst__eps-bars">
            {epsForecast.map((item) => (
              <div key={item.year} className="core-analyst__eps-item">
                <div
                  className="core-analyst__eps-bar"
                  style={{ height: `${(item.eps / epsMax) * 100}%` }}
                  title={`${item.year}: ${item.eps}`}
                />
                <span className="core-analyst__eps-value">{item.eps.toFixed(2)}</span>
                <span className="core-analyst__eps-year">{item.year}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="core-analyst__section">
          <h4 className="core-analyst__subtitle">{t('core.sentimentTitle')}</h4>
          <p className="core-analyst__label">{t('core.analystRating')}</p>
          <div className="core-analyst__rating-bar" role="img" aria-label={t('core.analystRating')}>
            <span className="core-analyst__rating-seg core-analyst__rating-seg--buy" style={{ width: `${rating.buy}%` }} />
            <span className="core-analyst__rating-seg core-analyst__rating-seg--hold" style={{ width: `${rating.hold}%` }} />
            <span className="core-analyst__rating-seg core-analyst__rating-seg--sell" style={{ width: `${rating.sell}%` }} />
          </div>
          <div className="core-analyst__rating-legend">
            <span>{t('core.buy')} {rating.buy}%</span>
            <span>{t('core.hold')} {rating.hold}%</span>
            <span>{t('core.sell')} {rating.sell}%</span>
          </div>

          <div className="core-analyst__target">
            <div>
              <p className="core-analyst__label">{t('core.targetPriceAvg')}</p>
              <p className="core-analyst__target-value core-analyst__target-value--avg">
                {formatCompactNumber(analyst.targetPriceAvg)} {analyst.currency}
              </p>
            </div>
            <div>
              <p className="core-analyst__label">{t('core.targetPriceCurrent')}</p>
              <p className="core-analyst__target-value">
                {formatCompactNumber(analyst.targetPriceCurrent)} {analyst.currency}
              </p>
            </div>
          </div>
        </section>
      </div>
    </CoreCard>
  );
}
