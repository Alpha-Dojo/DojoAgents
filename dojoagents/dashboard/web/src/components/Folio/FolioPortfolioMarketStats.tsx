import { useTranslation } from '../../hooks/useTranslation';
import { FOLIO_MARKETS } from '../../types/folio';
import type { FolioMarketSnapshotsByMarket } from '../../utils/folioPortfolioSnapshot';
import { formatCompactAmount, formatSignedPercent } from '../../utils/folioFormat';
import { MARKET_FLAG_IMAGE } from '../../utils/marketDisplay';
import type { MarketCode } from '../../types/market';

const MARKET_LABEL: Record<MarketCode, string> = {
  us: 'US',
  cn: 'CN',
  hk: 'HK',
};

interface FolioPortfolioMarketStatsProps {
  snapshots: FolioMarketSnapshotsByMarket | undefined;
}

function toneClass(value: number | null | undefined): string {
  if (value == null || value === 0) return 'folio-tone--muted';
  return value >= 0 ? 'sphere-table__up' : 'sphere-table__down';
}

function formatAssets(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value) || value <= 0) return '—';
  return formatCompactAmount(value);
}

function formatPct(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '0.00%';
  return formatSignedPercent(value);
}

export function FolioPortfolioMarketStats({ snapshots }: FolioPortfolioMarketStatsProps) {
  const { t } = useTranslation();

  return (
    <table className="folio-sidebar__stats-table">
      <colgroup>
        <col className="folio-sidebar__stats-col-market" />
        <col className="folio-sidebar__stats-col-candidates" />
        <col className="folio-sidebar__stats-col-holdings" />
        <col className="folio-sidebar__stats-col-net" />
        <col className="folio-sidebar__stats-col-today" />
        <col className="folio-sidebar__stats-col-total" />
      </colgroup>
      <thead>
        <tr>
          <th scope="col" className="folio-sidebar__stats-col-market" />
          <th scope="col" className="folio-sidebar__stats-col-candidates">
            {t('folio.sidebarCandidates')}
          </th>
          <th scope="col" className="folio-sidebar__stats-col-holdings">
            {t('folio.sidebarHoldings')}
          </th>
          <th scope="col" className="folio-sidebar__stats-col-net">
            {t('folio.sidebarNetValue')}
          </th>
          <th scope="col" className="folio-sidebar__stats-col-today">
            {t('folio.sidebarToday')}
          </th>
          <th scope="col" className="folio-sidebar__stats-col-total">
            {t('folio.sidebarTotalPnl')}
          </th>
        </tr>
      </thead>
      <tbody>
        {FOLIO_MARKETS.map((market) => {
          const snap = snapshots?.[market];
          return (
            <tr key={market}>
              <th scope="row" className="folio-sidebar__stats-market">
                <img className="folio-sidebar__stats-flag" src={MARKET_FLAG_IMAGE[market]} alt="" aria-hidden />
                <span className="folio-sidebar__stats-market-label">{MARKET_LABEL[market]}</span>
              </th>
              <td className="folio-sidebar__stats-count-cell folio-sidebar__stats-col-candidates folio-tone--muted">
                {snap?.candidateCount ?? 0}
              </td>
              <td className="folio-sidebar__stats-count-cell folio-sidebar__stats-col-holdings">
                {snap?.holdingCount ?? 0}
              </td>
              <td className="folio-sidebar__stats-num folio-sidebar__stats-col-net">
                {formatAssets(snap?.netValue)}
              </td>
              <td
                className={`folio-sidebar__stats-return-cell folio-sidebar__stats-col-today ${toneClass(snap?.todayChange)}`}
              >
                {formatPct(snap?.todayChange)}
              </td>
              <td
                className={`folio-sidebar__stats-return-cell folio-sidebar__stats-col-total ${toneClass(snap?.totalReturn)}`}
              >
                {formatPct(snap?.totalReturn)}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
