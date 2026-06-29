import { useMemo } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import type { FolioPortfolioDetail } from '../../api/dojoFolio';
import {
  computeRiskExposure,
  type RiskExposureRow,
  type RiskStatus,
} from '../../utils/folioRiskExposure';
import { LoadingIndicator } from '../ui/LoadingIndicator';

interface FolioRiskExposurePanelProps {
  portfolio: FolioPortfolioDetail;
  loading?: boolean;
  benchmarkSymbol: string | null;
}

const STATUS_ICON: Record<RiskStatus, string> = {
  red: '🔴',
  yellow: '🟡',
  green: '🟢',
};

const ROW_LABEL: Record<string, string> = {
  sector: 'folio.riskDimSector',
  holding: 'folio.riskDimHolding',
  market: 'folio.riskDimMarket',
  liquidity: 'folio.riskDimLiquidity',
  beta: 'folio.riskDimBeta',
};

function RiskTable({ rows }: { rows: RiskExposureRow[] }) {
  const { t } = useTranslation();

  return (
    <table className="folio-risk-exp__table">
      <colgroup>
        <col className="folio-risk-exp__col-status" />
        <col className="folio-risk-exp__col-dimension" />
        <col className="folio-risk-exp__col-current" />
        <col className="folio-risk-exp__col-limit" />
        <col className="folio-risk-exp__col-note" />
      </colgroup>
      <thead>
        <tr>
          <th scope="col" className="folio-risk-exp__head-status">
            {t('folio.riskColStatus')}
          </th>
          <th scope="col">{t('folio.riskColDimension')}</th>
          <th scope="col">{t('folio.riskColCurrent')}</th>
          <th scope="col">{t('folio.riskColLimit')}</th>
          <th scope="col">{t('folio.riskColNote')}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.id} className={`folio-risk-exp__row folio-risk-exp__row--${row.status}`}>
            <td className="folio-risk-exp__status" aria-label={row.status}>
              {STATUS_ICON[row.status]}
            </td>
            <th scope="row">{t(ROW_LABEL[row.id])}</th>
            <td className="folio-risk-exp__num">{row.current}</td>
            <td className="folio-risk-exp__num">{row.limit}</td>
            <td className="folio-risk-exp__note">
              {t(row.noteKey, row.noteVars ?? {})}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function FolioRiskExposurePanel({
  portfolio,
  loading = false,
  benchmarkSymbol,
}: FolioRiskExposurePanelProps) {
  const { t } = useTranslation();
  const exposure = useMemo(
    () => computeRiskExposure(portfolio.holdings, portfolio.performance, benchmarkSymbol),
    [benchmarkSymbol, portfolio.holdings, portfolio.performance],
  );

  if (loading && !exposure) {
    return (
      <LoadingIndicator
        className="folio-panel__status"
        label={t('folio.loading')}
        variant="panel"
      />
    );
  }
  if (!exposure) {
    return <p className="folio-panel__status">{t('folio.riskEmpty')}</p>;
  }

  const showAction = exposure.rows.some((row) => row.status === 'red' || row.status === 'yellow');

  return (
    <section className="folio-risk-exp" aria-busy={loading}>
      <RiskTable rows={exposure.rows} />
      <footer className="folio-risk-exp__insight">
        <span className="folio-risk-exp__insight-icon" aria-hidden>
          💡
        </span>
        <p>
          {t('folio.riskInsight', {
            sector: exposure.topSector ?? '—',
            weight: exposure.topSectorWeight.toFixed(1),
          })}
        </p>
        {showAction ? (
          <button type="button" className="folio-risk-exp__action" disabled>
            {t('folio.riskExecute')}
          </button>
        ) : null}
      </footer>
    </section>
  );
}
