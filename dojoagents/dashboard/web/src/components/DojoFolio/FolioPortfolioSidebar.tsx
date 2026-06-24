import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import type { FolioPortfolioListItem } from '../../hooks/useFolioPortfolios';
import type { FolioPortfolioHoldingsPreview } from '../../utils/folioPortfolioSearch';
import { formatCompactCurrency, formatSignedPercent } from '../../utils/folioFormat';
import { FolioConfirmDialog } from './FolioConfirmDialog';
import { FolioPortfolioSearch } from './FolioPortfolioSearch';

interface FolioPortfolioSidebarProps {
  portfolios: FolioPortfolioListItem[];
  allPortfolios: FolioPortfolioListItem[];
  holdingsByPortfolioId: Record<string, FolioPortfolioHoldingsPreview[]>;
  activeId: string;
  loading?: boolean;
  onSelect: (id: string) => void;
  onRename: (id: string, name: string) => void;
  onDelete: (id: string) => void;
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

function activateOnKeyboard(event: KeyboardEvent<HTMLDivElement>, onActivate: () => void) {
  if (event.currentTarget !== event.target) return;
  if (event.key !== 'Enter' && event.key !== ' ') return;
  event.preventDefault();
  onActivate();
}

export function FolioPortfolioSidebar({
  portfolios,
  allPortfolios,
  holdingsByPortfolioId,
  activeId,
  loading = false,
  onSelect,
  onRename,
  onDelete,
  onCreate,
  onSearchQueryChange,
}: FolioPortfolioSidebarProps) {
  const { t } = useTranslation();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);

  const pendingDelete = allPortfolios.find((item) => item.id === pendingDeleteId) ?? null;

  return (
    <aside className="folio-sidebar folio-card">
      <div className="folio-sidebar__body">
        <FolioPortfolioSearch
          portfolios={allPortfolios}
          holdingsByPortfolioId={holdingsByPortfolioId}
          onQueryChange={onSearchQueryChange}
          onSelectPortfolio={onSelect}
        />

        <button type="button" className="folio-sidebar__create" onClick={onCreate}>
          {t('folio.newPortfolio')}
        </button>

        {loading ? <p className="folio-sidebar__status">{t('folio.loading')}</p> : null}

        {portfolios.length > 0 ? (
          <ul className="folio-sidebar__list">
            {portfolios.map((portfolio) => {
              const active = portfolio.id === activeId;
              const positive = (portfolio.todayChange ?? 0) >= 0;

              return (
                <li key={portfolio.id}>
                  <div className={`folio-sidebar__item ${active ? 'folio-sidebar__item--active' : ''}`}>
                    <div
                      role="button"
                      tabIndex={0}
                      className="folio-sidebar__item-main"
                      aria-current={active ? 'true' : undefined}
                      onClick={() => onSelect(portfolio.id)}
                      onKeyDown={(event) => activateOnKeyboard(event, () => onSelect(portfolio.id))}
                    >
                      <div className="folio-sidebar__item-top">
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
                        {portfolio.subtitle ? (
                          <span className="folio-sidebar__item-sub">{portfolio.subtitle}</span>
                        ) : null}
                        {portfolio.kind === 'agent' ? (
                          <span className="folio-sidebar__badge">{t('folio.kindAgent')}</span>
                        ) : null}
                      </div>

                      <div className="folio-sidebar__item-stats">
                        <span className="folio-sidebar__stat-label">{t('folio.today')}</span>
                        <span
                          className={`folio-sidebar__stat-value ${
                            portfolio.todayChange == null
                              ? 'folio-tone--muted'
                              : `folio-tone--${positive ? 'up' : 'down'}`
                          }`}
                        >
                          {portfolio.todayChange == null
                            ? '—'
                            : formatSignedPercent(portfolio.todayChange)}
                        </span>
                        <span className="folio-sidebar__stat-label">{t('folio.netValueShort')}</span>
                        <span className="folio-sidebar__stat-value">
                          {portfolio.netValueUsd == null
                            ? '—'
                            : formatCompactCurrency(portfolio.netValueUsd, 'USD')}
                        </span>
                      </div>
                    </div>

                    <button
                      type="button"
                      className="folio-sidebar__delete"
                      aria-label={t('folio.deletePortfolio', { name: portfolio.name })}
                      title={t('folio.deletePortfolio', { name: portfolio.name })}
                      onClick={() => setPendingDeleteId(portfolio.id)}
                    >
                      ×
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        ) : null}
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
