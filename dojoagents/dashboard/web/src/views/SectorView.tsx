import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { SectorBottomPanel } from '../components/Sector/SectorBottomPanel';
import { SectorHero } from '../components/Sector/SectorHero';
import { LoadingIndicator } from '../components/ui/LoadingIndicator';
import {
  persistSectorViewState,
  readPersistedSectorScopeLevel,
  readPersistedSectorSelection,
} from '../cache/sectorViewState';
import { useSectorScopeMetrics } from '../hooks/useSectorScopeMetrics';
import { useSectorScopePerformanceAll } from '../hooks/useSectorScopePerformanceAll';
import { useSectorTaxonomy } from '../hooks/useSectorTaxonomy';
import { useSectorScale } from '../hooks/useSectorViewportLayout';
import { useTranslation } from '../hooks/useTranslation';
import {
  isSectorViewBootstrapped,
  markSectorViewBootstrapped,
  resolveJumpSelection,
  SECTOR_NAVIGATE_EVENT,
} from '../navigation/sectorContext';
import type { AppTab } from '../navigation/appTab';
import type { SectorPathSelection, SectorTaxonomyDocument } from '../types/sectorTaxonomy';
import type { SectorLevelKey } from '../types/sector';
import {
  findSectorPathByIds,
  getSectorDefaultSelection,
} from '../utils/sectorTaxonomy';
import './SectorView.css';

interface SectorViewProps {
  onNavigateTab?: (tab: AppTab) => void;
}

function resolveFallbackSelection(taxonomy: SectorTaxonomyDocument): SectorPathSelection {
  const persisted = readPersistedSectorSelection();
  if (persisted && findSectorPathByIds(taxonomy, persisted)) {
    return persisted;
  }
  return getSectorDefaultSelection(taxonomy);
}

export function SectorView({ onNavigateTab }: SectorViewProps) {
  const { t } = useTranslation();
  const { taxonomy, loading, error } = useSectorTaxonomy();
  const [selection, setSelection] = useState<SectorPathSelection | null>(null);
  const [scopeLevel, setScopeLevel] = useState<SectorLevelKey>(readPersistedSectorScopeLevel);
  const [navTick, setNavTick] = useState(0);
  const viewRef = useRef<HTMLElement>(null);
  const scaleVars = useSectorScale(viewRef);

  useEffect(() => {
    const onNavigate = () => setNavTick((tick) => tick + 1);
    window.addEventListener(SECTOR_NAVIGATE_EVENT, onNavigate);
    return () => window.removeEventListener(SECTOR_NAVIGATE_EVENT, onNavigate);
  }, []);

  useEffect(() => {
    if (!taxonomy) return;

    const jumpSelection = resolveJumpSelection(taxonomy);
    if (jumpSelection) {
      setSelection(jumpSelection);
      setScopeLevel('L3');
      markSectorViewBootstrapped();
      return;
    }

    if (isSectorViewBootstrapped()) {
      const persisted = readPersistedSectorSelection();
      if (persisted && findSectorPathByIds(taxonomy, persisted)) {
        setSelection(persisted);
        setScopeLevel(readPersistedSectorScopeLevel());
        return;
      }
      setSelection((current) => current ?? resolveFallbackSelection(taxonomy));
      return;
    }

    setSelection(resolveFallbackSelection(taxonomy));
    markSectorViewBootstrapped();
  }, [taxonomy, navTick]);

  useEffect(() => {
    if (selection) persistSectorViewState(selection, scopeLevel);
  }, [selection, scopeLevel]);

  const prevSelectionKeyRef = useRef<string | null>(null);
  useEffect(() => {
    const key = selection
      ? `${selection.level1Id}:${selection.level2Id}:${selection.level3Id}`
      : null;
    if (prevSelectionKeyRef.current != null && prevSelectionKeyRef.current !== key) {
      setScopeLevel('L3');
    }
    prevSelectionKeyRef.current = key;
  }, [selection?.level1Id, selection?.level2Id, selection?.level3Id]);

  const path = useMemo(() => {
    if (!taxonomy || !selection) return null;
    return findSectorPathByIds(taxonomy, selection);
  }, [taxonomy, selection]);

  const { metrics, loading: metricsLoading } = useSectorScopeMetrics(selection);
  const { performanceByLevel, loading: performanceLoading } = useSectorScopePerformanceAll(selection);

  if (loading && !taxonomy) {
    return (
      <section className="sector-view sector-view--loading">
        <LoadingIndicator label={t('sectorPage.loading')} variant="page" />
      </section>
    );
  }

  if ((error && !taxonomy) || !taxonomy || !selection || !path) {
    return (
      <section className="sector-view sector-view--error">
        <p>{error ?? t('sectorPage.loadFailed')}</p>
      </section>
    );
  }

  return (
    <section
      ref={viewRef}
      className="sector-view"
      aria-label="Sectors"
      style={scaleVars as CSSProperties}
    >
      <div className="sector-view__grid">
        <SectorHero
          taxonomy={taxonomy}
          selection={selection}
          onSelectionChange={setSelection}
          path={path}
          metrics={metrics}
          metricsLoading={metricsLoading}
          performanceByLevel={performanceByLevel}
          performanceLoading={performanceLoading}
          selectedLevel={scopeLevel}
          onSelectLevel={setScopeLevel}
        />
        {!performanceLoading ? (
          <SectorBottomPanel selection={selection} scope={scopeLevel} onNavigateTab={onNavigateTab} />
        ) : null}
      </div>
    </section>
  );
}
