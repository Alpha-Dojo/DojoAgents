import { useTranslation } from '../../hooks/useTranslation';
import type { EntityRiskSnapshot } from '../../types/entity';
import { EntityCard } from './EntityCard';

interface EntityRiskPanelProps {
  risk: EntityRiskSnapshot;
}

export function EntityRiskPanel({ risk }: EntityRiskPanelProps) {
  const { t } = useTranslation();

  return (
    <EntityCard title={t('entityPage.riskTitle')} className="entity-card--risk">
      <div className="core-risk">
        <div className="core-risk__main">
          <section className="core-risk__block">
            <h4 className="core-risk__subtitle">{t('entityPage.insiderActivity')}</h4>
            {risk.insiderTrades.length === 0 ? (
              <p className="core-risk__text core-risk__text--dim">{t('entityPage.noInsiderActivity')}</p>
            ) : (
              <ul className="core-risk__insider-list">
                {risk.insiderTrades.map((trade) => (
                  <li key={`${trade.date}-${trade.executive}`} className="core-risk__insider-item">
                    <span className="core-risk__insider-date">{trade.date}</span>
                    <span className="core-risk__insider-detail">
                      {trade.executive} {t(`core.insider.${trade.actionKey}` as 'entityPage.insider.sold')}{' '}
                      {trade.shares.toLocaleString()} {t('entityPage.shares')}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>

        <aside className={`core-risk__status ${risk.noMajorWarnings ? 'core-risk__status--ok' : 'core-risk__status--warn'}`}>
          <span className="core-risk__status-icon" aria-hidden>
            {risk.noMajorWarnings ? '✓' : '!'}
          </span>
          <p className="core-risk__status-text">
            {risk.noMajorWarnings ? t('entityPage.noMajorWarnings') : t('entityPage.warningsPresent')}
          </p>
        </aside>
      </div>
    </EntityCard>
  );
}
