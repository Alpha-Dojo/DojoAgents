import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import type { SectorItem, SectorMemberItem } from '../../types/dojoMesh';
import { formatMarketCap, formatStockPrice } from '../../utils/marketStats';

interface SectorRowProps {
  sector: SectorItem;
  variant: 'gain' | 'loss';
  selected?: boolean;
  linked?: boolean;
  missing?: boolean;
  onSelect?: () => void;
  onJump?: () => void;
  onTickerClick?: (member: SectorMemberItem, sector: SectorItem) => void;
}

type MemberSortKey = 'cap' | 'change';
type MemberSortDir = 'asc' | 'desc';

function sortMembers(
  members: SectorMemberItem[],
  key: MemberSortKey,
  dir: MemberSortDir,
): SectorMemberItem[] {
  const factor = dir === 'asc' ? 1 : -1;
  return [...members].sort((a, b) => {
    const av = key === 'cap' ? a.market_cap ?? 0 : a.change_percent;
    const bv = key === 'cap' ? b.market_cap ?? 0 : b.change_percent;
    if (av === bv) return a.ticker.localeCompare(b.ticker);
    return (av - bv) * factor;
  });
}

function SortIndicator({ active, dir }: { active: boolean; dir: MemberSortDir }) {
  if (!active) {
    return (
      <span className="mesh-member-sort-btn__icon mesh-member-sort-btn__icon--idle" aria-hidden>
        ↕
      </span>
    );
  }
  return (
    <span className="mesh-member-sort-btn__icon" aria-hidden>
      {dir === 'asc' ? '↑' : '↓'}
    </span>
  );
}

function ExpandIcon({ open }: { open: boolean }) {
  return (
    <svg
      className={`mesh-sector-row__icon ${open ? 'mesh-sector-row__icon--open' : ''}`}
      width="12"
      height="12"
      viewBox="0 0 12 12"
      aria-hidden
    >
      <path
        d="M3 4.5L6 7.5L9 4.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function JumpIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden>
      <path
        d="M4 2.5h5.5V8M9.5 2.5L2.5 9.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function SectorRow({
  sector,
  variant,
  selected,
  linked,
  missing,
  onSelect,
  onJump,
  onTickerClick,
}: SectorRowProps) {
  const { t, text } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const [sortKey, setSortKey] = useState<MemberSortKey>('cap');
  const [sortDir, setSortDir] = useState<MemberSortDir>('desc');
  const positive = sector.change_percent >= 0;
  const sign = positive ? '+' : '';
  const sectorLabel = text(sector.name);
  const members = sector.members?.length
    ? sector.members
    : sector.sample_tickers.map((ticker) => ({
        ticker,
        name: { zh: ticker, en: ticker },
        last_price: undefined,
        market_cap: undefined,
        change_percent: sector.change_percent,
      }));
  const memberCount = sector.member_count ?? members.length;
  const sortedMembers = useMemo(
    () => sortMembers(members, sortKey, sortDir),
    [members, sortKey, sortDir],
  );

  useEffect(() => {
    setSortKey('cap');
    setSortDir('desc');
  }, [sector.concept_code]);

  const toggleSort = (key: MemberSortKey) => {
    if (sortKey === key) {
      setSortDir((dir) => (dir === 'asc' ? 'desc' : 'asc'));
      return;
    }
    setSortKey(key);
    setSortDir('desc');
  };

  const rowClass = [
    'mesh-sector-row',
    `mesh-sector-row--${variant}`,
    selected ? 'mesh-sector-row--selected' : '',
    linked ? 'mesh-sector-row--linked' : '',
    missing ? 'mesh-sector-row--missing' : '',
    expanded ? 'mesh-sector-row--expanded' : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div className={rowClass}>
      <div className="mesh-sector-row__shell">
        {missing ? (
          <div className="mesh-sector-row__main mesh-sector-row__main--static">
            <div className="mesh-sector-row__body">
              <div className="mesh-sector-row__name-row">
                <span className="mesh-sector-row__name">
                  {linked ? <span className="mesh-sector-row__link-badge">{t('sector.link')}</span> : null}
                  {sectorLabel}
                </span>
              </div>
              <span className="mesh-sector-row__missing-hint">{t('sector.noSectorInMarket')}</span>
            </div>
          </div>
        ) : (
          <button
            type="button"
            className="mesh-sector-row__main"
            onClick={onSelect}
            title={t('sector.crossMarket')}
          >
            <div className="mesh-sector-row__body">
              <div className="mesh-sector-row__name-row">
                <span className="mesh-sector-row__name">
                  {linked ? <span className="mesh-sector-row__link-badge">{t('sector.link')}</span> : null}
                  {sectorLabel}
                </span>
                <span className={`mesh-sector-row__chg mesh-sector-row__chg--${variant}`}>
                  {sign}
                  {sector.change_percent.toFixed(2)}%
                </span>
              </div>
              {!expanded && sector.sample_tickers.length > 0 ? (
                <span className="mesh-sector-row__tickers">{sector.sample_tickers.join(', ')}</span>
              ) : null}
            </div>
            <div className="mesh-sector-row__bar" aria-hidden>
              <div
                className={`mesh-sector-row__fill mesh-sector-row__fill--${variant}`}
                style={{ width: `${sector.strength}%` }}
              />
            </div>
          </button>
        )}
        {!missing ? (
          <div className="mesh-sector-row__actions">
            <button
              type="button"
              className={`mesh-sector-row__action ${expanded ? 'mesh-sector-row__action--active' : ''}`}
              aria-expanded={expanded}
              aria-label={expanded ? t('sector.collapse') : t('sector.expand')}
              title={expanded ? t('sector.collapse') : t('sector.expand')}
              onClick={() => setExpanded((v) => !v)}
            >
              <ExpandIcon open={expanded} />
            </button>
            <button
              type="button"
              className="mesh-sector-row__action mesh-sector-row__action--jump"
              aria-label={t('sector.jumpSphere')}
              title={t('sector.jumpSphere')}
              onClick={onJump}
            >
              <JumpIcon />
            </button>
          </div>
        ) : null}
      </div>
      {!missing && expanded ? (
        <div className="mesh-sector-row__members">
          <div className="mesh-sector-row__members-table">
            <div className="mesh-sector-row__members-colhead">
              <span className="mesh-sector-row__member-col mesh-sector-row__member-col--id mesh-sector-row__member-col--title">
                {t('sector.membersCount', { count: memberCount })}
              </span>
              <span className="mesh-sector-row__member-col mesh-sector-row__member-col--price">
                {t('sector.price')}
              </span>
              <button
                type="button"
                className={`mesh-member-sort-btn mesh-sector-row__member-col mesh-sector-row__member-col--cap ${sortKey === 'cap' ? 'mesh-member-sort-btn--active' : ''}`}
                aria-label={t('sector.sortByCap')}
                title={t('sector.sortByCap')}
                onClick={() => toggleSort('cap')}
              >
                {t('sector.marketCap')}
                <SortIndicator active={sortKey === 'cap'} dir={sortDir} />
              </button>
              <button
                type="button"
                className={`mesh-member-sort-btn mesh-sector-row__member-col mesh-sector-row__member-col--chg ${sortKey === 'change' ? 'mesh-member-sort-btn--active' : ''}`}
                aria-label={t('sector.sortByChange')}
                title={t('sector.sortByChange')}
                onClick={() => toggleSort('change')}
              >
                {t('sector.change')}
                <SortIndicator active={sortKey === 'change'} dir={sortDir} />
              </button>
            </div>
            <ul className="mesh-sector-row__members-list">
            {sortedMembers.map((m) => {
              const up = m.change_percent >= 0;
              const displayName = m.name ? text(m.name) : m.ticker;
              const showBracketName = m.name && displayName !== m.ticker;
              return (
                <li key={m.ticker} className="mesh-sector-row__member">
                  <div
                    className="mesh-sector-row__member-col mesh-sector-row__member-col--id"
                    title={m.name ? `${m.ticker} ${text(m.name)}` : m.ticker}
                  >
                    <span className="mesh-sector-row__member-label">
                      <button
                        type="button"
                        className="mesh-sector-row__member-ticker mesh-sector-row__member-ticker--link"
                        title={t('sector.jumpCore')}
                        aria-label={`${t('sector.jumpCore')}: ${m.ticker}`}
                        onClick={() => onTickerClick?.(m, sector)}
                      >
                        {m.ticker}
                      </button>
                      {showBracketName ? (
                        <span className="mesh-sector-row__member-name">[{displayName}]</span>
                      ) : null}
                    </span>
                  </div>
                    <span className="mesh-sector-row__member-col mesh-sector-row__member-col--price">
                      {formatStockPrice(m.last_price)}
                    </span>
                    <span className="mesh-sector-row__member-col mesh-sector-row__member-col--cap">
                      {m.market_cap != null && m.market_cap > 0
                        ? formatMarketCap(m.market_cap)
                        : '—'}
                    </span>
                    <span
                      className={`mesh-sector-row__member-col mesh-sector-row__member-col--chg mesh-sector-row__member-chg ${up ? 'mesh-sector-row__member-chg--up' : 'mesh-sector-row__member-chg--down'}`}
                    >
                      {up ? '+' : ''}
                      {m.change_percent.toFixed(2)}%
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>
        </div>
      ) : null}
    </div>
  );
}
