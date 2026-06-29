import { useEffect, useRef, useState } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import type { FolioPortfolioListItem } from '../../hooks/useFolioPortfolios';
import type { FolioPortfolioHoldingsPreview } from '../../utils/folioPortfolioSearch';
import { LoadingIndicator } from '../ui/LoadingIndicator';
import { FolioConfirmDialog } from './FolioConfirmDialog';
import { FolioPortfolioMarketStats } from './FolioPortfolioMarketStats';
import { FolioPortfolioSearch } from './FolioPortfolioSearch';
import { ChevronIcon, PinIcon, TrashIcon } from './FolioSidebarIcons';

interface FolioPortfolioSidebarProps {
  portfolios: FolioPortfolioListItem[];
  allPortfolios: FolioPortfolioListItem[];
  holdingsByPortfolioId: Record<string, FolioPortfolioHoldingsPreview[]>;
  activeId: string;
  loading?: boolean;
  creating?: boolean;
  createError?: string | null;
  onSelect: (id: string) => void;
  onRename: (id: string, name: string) => void;
  onDelete: (id: string) => void;
  onTogglePin: (id: string, pinned: boolean) => void;
  onCreate?: () => void;
  onSearchQueryChange: (query: string) => void;
}

function EditablePortfolioName({
  name,
  editing,
  onStartEdit,
  onCommit,
  onCancel,
}: {
  name: string;
  editing: boolean;
  onStartEdit: () => void;
  onCommit: (value: string) => void;
  onCancel: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [draft, setDraft] = useState(name);

  useEffect(() => {
    if (editing) {
      setDraft(name);
      inputRef.current?.focus();
      inputRef.current?.select();
    }
  }, [editing, name]);

  if (editing) {
    return (
      <input
        ref={inputRef}
        className="folio-sidebar__name-input"
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onClick={(event) => event.stopPropagation()}
        onKeyDown={(event) => {
          if (event.key === 'Enter') {
            event.preventDefault();
            onCommit(draft);
          }
          if (event.key === 'Escape') {
            event.preventDefault();
            onCancel();
          }
        }}
        onBlur={() => onCommit(draft)}
      />
    );
  }

  return (
    <button
      type="button"
      className="folio-sidebar__name-button"
      onClick={(event) => {
        event.stopPropagation();
        onStartEdit();
      }}
    >
      {name}
    </button>
  );
}

function CreatePortfolioIcon() {
  return (
    <svg
      className="folio-sidebar__create-icon"
      width="11"
      height="11"
      viewBox="0 0 11 11"
      aria-hidden
    >
      <rect
        x="0.75"
        y="0.75"
        width="9.5"
        height="9.5"
        rx="2"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.1"
      />
      <path
        d="M5.5 3.25v4.5M3.25 5.5h4.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.1"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function FolioPortfolioSidebar({
  portfolios,
  allPortfolios,
  holdingsByPortfolioId,
  activeId,
  loading = false,
  creating = false,
  createError = null,
  onSelect,
  onRename,
  onDelete,
  onTogglePin,
  onCreate,
  onSearchQueryChange,
}: FolioPortfolioSidebarProps) {
  const { t } = useTranslation();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const [collapsedPortfolioIds, setCollapsedPortfolioIds] = useState<Set<string>>(
    () => new Set(),
  );

  const pendingDelete = allPortfolios.find((item) => item.id === pendingDeleteId) ?? null;
  const allVisibleCollapsed =
    portfolios.length > 0 &&
    portfolios.every((portfolio) => collapsedPortfolioIds.has(portfolio.id));

  useEffect(() => {
    const portfolioIds = new Set(allPortfolios.map((portfolio) => portfolio.id));
    setCollapsedPortfolioIds((current) => {
      const next = new Set([...current].filter((id) => portfolioIds.has(id)));
      return next.size === current.size ? current : next;
    });
  }, [allPortfolios]);

  const togglePortfolioCollapsed = (portfolioId: string) => {
    setCollapsedPortfolioIds((current) => {
      const next = new Set(current);
      if (next.has(portfolioId)) {
        next.delete(portfolioId);
      } else {
        next.add(portfolioId);
      }
      return next;
    });
  };

  const toggleAllPortfolios = () => {
    setCollapsedPortfolioIds((current) => {
      const next = new Set(current);
      portfolios.forEach((portfolio) => {
        if (allVisibleCollapsed) {
          next.delete(portfolio.id);
        } else {
          next.add(portfolio.id);
        }
      });
      return next;
    });
  };

  return (
    <aside className="folio-sidebar folio-card">
      <div className="folio-sidebar__body">
        <div className="folio-sidebar__search-row">
          <FolioPortfolioSearch
            portfolios={allPortfolios}
            holdingsByPortfolioId={holdingsByPortfolioId}
            onQueryChange={onSearchQueryChange}
            onSelectPortfolio={onSelect}
          />
          <button
            type="button"
            className="folio-sidebar__collapse-all"
            disabled={portfolios.length === 0}
            aria-label={
              allVisibleCollapsed
                ? t('folio.expandAllPortfolios')
                : t('folio.collapseAllPortfolios')
            }
            title={
              allVisibleCollapsed
                ? t('folio.expandAllPortfolios')
                : t('folio.collapseAllPortfolios')
            }
            onClick={toggleAllPortfolios}
          >
            <ChevronIcon expanded={!allVisibleCollapsed} />
            <ChevronIcon expanded={!allVisibleCollapsed} />
          </button>
        </div>

        {loading ? (
          <LoadingIndicator
            className="folio-sidebar__status"
            label={t('folio.loading')}
            variant="panel"
          />
        ) : null}

        {portfolios.length > 0 ? (
          <ul className="folio-sidebar__list">
            {portfolios.map((portfolio) => {
              const active = portfolio.id === activeId;
              const collapsed = collapsedPortfolioIds.has(portfolio.id);
              const hasSnapshots =
                portfolio.marketSnapshots &&
                Object.keys(portfolio.marketSnapshots).length > 0;

              return (
                <li key={portfolio.id}>
                  <div
                    className={`folio-sidebar__item ${active ? 'folio-sidebar__item--active' : ''} ${
                      portfolio.pinned ? 'folio-sidebar__item--pinned' : ''
                    } ${collapsed ? 'folio-sidebar__item--collapsed' : ''}`}
                  >
                    <button
                      type="button"
                      className="folio-sidebar__item-select"
                      aria-current={active ? 'true' : undefined}
                      aria-label={portfolio.name}
                      onClick={() => onSelect(portfolio.id)}
                    />
                    <div className="folio-sidebar__item-main">
                      <div className="folio-sidebar__item-header">
                        <div className="folio-sidebar__item-title-wrap">
                          <div className="folio-sidebar__item-title-row">
                            <EditablePortfolioName
                              name={portfolio.name}
                              editing={editingId === portfolio.id}
                              onStartEdit={() => setEditingId(portfolio.id)}
                              onCommit={(value) => {
                                onRename(portfolio.id, value);
                                setEditingId(null);
                              }}
                              onCancel={() => setEditingId(null)}
                            />
                            {portfolio.kind === 'agent' ? (
                              <span className="folio-sidebar__badge folio-sidebar__badge--agent">
                                {t('folio.kindAgent')}
                              </span>
                            ) : (
                              <span className="folio-sidebar__badge folio-sidebar__badge--manual">
                                {t('folio.kindManual')}
                              </span>
                            )}
                          </div>
                          {portfolio.subtitle && portfolio.kind !== 'agent' ? (
                            <span className="folio-sidebar__item-sub">{portfolio.subtitle}</span>
                          ) : null}
                        </div>

                        <div className="folio-sidebar__item-actions">
                          <button
                            type="button"
                            className="folio-sidebar__icon-btn folio-sidebar__collapse-one"
                            aria-expanded={!collapsed}
                            aria-label={
                              collapsed
                                ? t('folio.expandPortfolio', { name: portfolio.name })
                                : t('folio.collapsePortfolio', { name: portfolio.name })
                            }
                            title={
                              collapsed
                                ? t('folio.expandPortfolio', { name: portfolio.name })
                                : t('folio.collapsePortfolio', { name: portfolio.name })
                            }
                            onClick={(event) => {
                              event.stopPropagation();
                              togglePortfolioCollapsed(portfolio.id);
                            }}
                          >
                            <ChevronIcon expanded={!collapsed} />
                          </button>
                          <button
                            type="button"
                            className={`folio-sidebar__icon-btn ${
                              portfolio.pinned ? 'folio-sidebar__icon-btn--active' : ''
                            }`}
                            aria-label={
                              portfolio.pinned ? t('folio.unpinPortfolio') : t('folio.pinPortfolio')
                            }
                            title={
                              portfolio.pinned ? t('folio.unpinPortfolio') : t('folio.pinPortfolio')
                            }
                            onClick={(event) => {
                              event.stopPropagation();
                              onTogglePin(portfolio.id, !portfolio.pinned);
                            }}
                          >
                            <PinIcon filled={portfolio.pinned} />
                          </button>
                          <button
                            type="button"
                            className="folio-sidebar__icon-btn folio-sidebar__icon-btn--danger"
                            aria-label={t('folio.deletePortfolio', { name: portfolio.name })}
                            title={t('folio.deletePortfolio', { name: portfolio.name })}
                            onClick={(event) => {
                              event.stopPropagation();
                              setPendingDeleteId(portfolio.id);
                            }}
                          >
                            <TrashIcon />
                          </button>
                        </div>
                      </div>

                      {!collapsed ? (
                        hasSnapshots ? (
                          <FolioPortfolioMarketStats snapshots={portfolio.marketSnapshots!} />
                        ) : null
                      ) : null}
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        ) : null}
      </div>

      <div className="folio-sidebar__footer">
        {createError ? (
          <p className="folio-sidebar__create-error" role="alert">
            {createError}
          </p>
        ) : null}
        <button
          type="button"
          className="folio-sidebar__create"
          disabled={creating}
          aria-busy={creating}
          onClick={onCreate}
        >
          <CreatePortfolioIcon />
          <span className="folio-sidebar__create-label">
            {creating ? t('folio.creatingPortfolio') : t('folio.newPortfolio')}
          </span>
        </button>
      </div>

      <FolioConfirmDialog
        open={pendingDelete != null}
        title={t('folio.deleteConfirmTitle')}
        message={t('folio.deleteConfirmMessage', { name: pendingDelete?.name ?? '' })}
        confirmLabel={t('folio.confirmDelete')}
        onConfirm={() => {
          if (pendingDeleteId) onDelete(pendingDeleteId);
          setPendingDeleteId(null);
        }}
        onCancel={() => setPendingDeleteId(null)}
      />
    </aside>
  );
}
