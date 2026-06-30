import { useTranslation } from '../../hooks/useTranslation';
import type { EntityAnalystSnapshot } from '../../types/entity';
import { formatCompactNumber } from '../../utils/entityCharts';
import { EntityCard } from './EntityCard';

interface EntityAnalystPanelProps {
  analyst: EntityAnalystSnapshot;
}

export function EntityAnalystPanel({ analyst }: EntityAnalystPanelProps) {
  const { t } = useTranslation();
  const { rating, epsForecast } = analyst;
  const epsMax = Math.max(...epsForecast.map((e) => e.eps), 1);

  return (
    <EntityCard title={t('entityPage.analystTitle')} className="entity-card--analyst">
      <div className="core-analyst">
        <section className="core-analyst__section">
          <h4 className="core-analyst__subtitle">{t('entityPage.epsForecastTitle')}</h4>
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
          <h4 className="core-analyst__subtitle">{t('entityPage.sentimentTitle')}</h4>
          <p className="core-analyst__label">{t('entityPage.analystRating')}</p>
          <div className="core-analyst__rating-bar" role="img" aria-label={t('entityPage.analystRating')}>
            <span className="core-analyst__rating-seg core-analyst__rating-seg--buy" style={{ width: `${rating.buy}%` }} />
            <span className="core-analyst__rating-seg core-analyst__rating-seg--hold" style={{ width: `${rating.hold}%` }} />
            <span className="core-analyst__rating-seg core-analyst__rating-seg--sell" style={{ width: `${rating.sell}%` }} />
          </div>
          <div className="core-analyst__rating-legend">
            <span>{t('entityPage.buy')} {rating.buy}%</span>
            <span>{t('entityPage.hold')} {rating.hold}%</span>
            <span>{t('entityPage.sell')} {rating.sell}%</span>
          </div>

          <div className="core-analyst__target">
            <div>
              <p className="core-analyst__label">{t('entityPage.targetPriceAvg')}</p>
              <p className="core-analyst__target-value core-analyst__target-value--avg">
                {formatCompactNumber(analyst.targetPriceAvg)} {analyst.currency}
              </p>
            </div>
            <div>
              <p className="core-analyst__label">{t('entityPage.targetPriceCurrent')}</p>
              <p className="core-analyst__target-value">
                {formatCompactNumber(analyst.targetPriceCurrent)} {analyst.currency}
              </p>
            </div>
          </div>
        </section>
      </div>
    </EntityCard>
  );
}
