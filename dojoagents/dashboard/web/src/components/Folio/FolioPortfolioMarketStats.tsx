import { useTranslation } from '../../hooks/useTranslation';
import type { FolioMarketSnapshot } from '../../utils/folioPortfolioSnapshot';
import { marketsWithSnapshots } from '../../utils/folioPortfolioSnapshot';
import { formatCompactAmount, formatSignedPercent } from '../../utils/folioFormat';
import { MARKET_FLAG } from '../../utils/marketDisplay';
import type { MarketCode } from '../../types/market';

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

type StatsRow = {
  market: MarketCode | null;
  snap: FolioMarketSnapshot | null;
};

function buildStatsRows(
  snapshots: Partial<Record<MarketCode, FolioMarketSnapshot>>,
): StatsRow[] {
  const markets = marketsWithSnapshots(snapshots);
  if (markets.length > 0) {
    return markets.map((market) => ({ market, snap: snapshots[market] ?? null }));
  }
  return [{ market: null, snap: null }];
}

export function FolioPortfolioMarketStats({ snapshots }: FolioPortfolioMarketStatsProps) {
  const { t } = useTranslation();
  const rows = buildStatsRows(snapshots);

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
        {rows.map((row) => {
          const key = row.market ?? 'empty';
          const snap = row.snap;
          return (
            <tr key={key}>
              <th scope="row" className="folio-sidebar__stats-market">
                {row.market ? (
                  <>
                    <span className="folio-sidebar__stats-flag" aria-hidden>
                      {MARKET_FLAG[row.market]}
                    </span>
                    <span className="folio-sidebar__stats-market-label">{MARKET_LABEL[row.market]}</span>
                  </>
                ) : (
                  <span className="folio-sidebar__stats-market-label">—</span>
                )}
              </th>
              <td className="folio-sidebar__stats-count-cell folio-sidebar__stats-col-candidates folio-tone--muted">
                —
              </td>
              <td className="folio-sidebar__stats-count-cell folio-sidebar__stats-col-holdings">
                {snap?.holdingCount != null && snap.holdingCount > 0 ? snap.holdingCount : '—'}
              </td>
              <td className="folio-sidebar__stats-num folio-sidebar__stats-col-net">
                {snap != null && snap.netValue > 0 ? formatCompactAmount(snap.netValue) : '—'}
              </td>
              <td
                className={`folio-sidebar__stats-return-cell folio-sidebar__stats-col-today ${toneClass(snap?.todayChange)}`}
              >
                {snap?.todayChange == null ? '—' : formatSignedPercent(snap.todayChange)}
              </td>
              <td
                className={`folio-sidebar__stats-return-cell folio-sidebar__stats-col-total ${toneClass(snap?.totalReturn)}`}
              >
                {snap?.totalReturn == null ? '—' : formatSignedPercent(snap.totalReturn)}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
