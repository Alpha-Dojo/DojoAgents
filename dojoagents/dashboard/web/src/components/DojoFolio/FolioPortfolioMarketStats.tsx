import { useTranslation } from '../../hooks/useTranslation';
import type { FolioMarketSnapshot } from '../../utils/folioPortfolioSnapshot';
import { marketsWithSnapshots } from '../../utils/folioPortfolioSnapshot';
import { formatCompactAmount, formatSignedPercent } from '../../utils/folioFormat';
import { MARKET_FLAG } from '../../utils/marketDisplay';
import type { MarketCode } from '../../types/dojoMesh';

const MARKET_LABEL: Record<MarketCode, string> = {
  us: 'US',
  cn: 'CN',
  hk: 'HK',
};

interface FolioPortfolioMarketStatsProps {
  snapshots: Partial<Record<MarketCode, FolioMarketSnapshot>>;
}

function toneClass(value: number | null | undefined): string {
  if (value == null) return 'folio-tone--muted';
  return value >= 0 ? 'sphere-table__up' : 'sphere-table__down';
}

export function FolioPortfolioMarketStats({ snapshots }: FolioPortfolioMarketStatsProps) {
  const { t } = useTranslation();
  const markets = marketsWithSnapshots(snapshots);
  if (markets.length === 0) return null;

  return (
    <table className="folio-sidebar__stats-table">
      <thead>
        <tr>
          <th scope="col" className="folio-sidebar__stats-col-market" />
          <th scope="col" className="folio-sidebar__stats-col-count">
            {t('folio.sidebarHoldings')}
          </th>
          <th scope="col">{t('folio.sidebarToday')}</th>
          <th scope="col">{t('folio.sidebarNetValue')}</th>
          <th scope="col">{t('folio.sidebarTotalReturn')}</th>
        </tr>
      </thead>
      <tbody>
        {markets.map((market) => {
          const snap = snapshots[market];
          if (!snap) return null;
          return (
            <tr key={market}>
              <th scope="row" className="folio-sidebar__stats-market">
                <span className="folio-sidebar__stats-flag" aria-hidden>
                  {MARKET_FLAG[market]}
                </span>
                <span className="folio-sidebar__stats-market-label">{MARKET_LABEL[market]}</span>
              </th>
              <td className="folio-sidebar__stats-count-cell">{snap.holdingCount}</td>
              <td className={toneClass(snap.todayChange)}>
                {snap.todayChange == null ? '—' : formatSignedPercent(snap.todayChange)}
              </td>
              <td className="folio-sidebar__stats-num">
                {snap.netValue > 0 ? formatCompactAmount(snap.netValue) : '—'}
              </td>
              <td className={`folio-sidebar__stats-return-cell ${toneClass(snap.totalReturn)}`}>
                {snap.totalReturn == null ? '—' : formatSignedPercent(snap.totalReturn)}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
