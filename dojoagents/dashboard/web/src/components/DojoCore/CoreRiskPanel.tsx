import { useTranslation } from '../../hooks/useTranslation';
import type { CoreRiskSnapshot } from '../../types/dojoCore';
import { CoreCard } from './CoreCard';

interface CoreRiskPanelProps {
  risk: CoreRiskSnapshot;
}

export function CoreRiskPanel({ risk }: CoreRiskPanelProps) {
  const { t } = useTranslation();

  return (
    <CoreCard title={t('core.riskTitle')} className="core-card--risk">
      <div className="core-risk">
        <div className="core-risk__main">
          <section className="core-risk__block">
            <h4 className="core-risk__subtitle">{t('core.insiderActivity')}</h4>
            {risk.insiderTrades.length === 0 ? (
              <p className="core-risk__text core-risk__text--dim">{t('core.noInsiderActivity')}</p>
            ) : (
              <ul className="core-risk__insider-list">
                {risk.insiderTrades.map((trade) => (
                  <li key={`${trade.date}-${trade.executive}`} className="core-risk__insider-item">
                    <span className="core-risk__insider-date">{trade.date}</span>
                    <span className="core-risk__insider-detail">
                      {trade.executive} {t(`core.insider.${trade.actionKey}` as 'core.insider.sold')}{' '}
                      {trade.shares.toLocaleString()} {t('core.shares')}
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
            {risk.noMajorWarnings ? t('core.noMajorWarnings') : t('core.warningsPresent')}
          </p>
        </aside>
      </div>
    </CoreCard>
  );
}
