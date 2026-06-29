import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { SphereBottomPanel } from '../components/DojoSphere/SphereBottomPanel';
import { SphereSectorHero } from '../components/DojoSphere/SphereSectorHero';
import { LoadingIndicator } from '../components/ui/LoadingIndicator';
import {
  persistSphereViewState,
  readPersistedSphereScopeLevel,
  readPersistedSphereSelection,
} from '../cache/sphereViewState';
import { useSectorScopeMetrics } from '../hooks/useSectorScopeMetrics';
import { useSectorScopePerformanceAll } from '../hooks/useSectorScopePerformanceAll';
import { useSectorTaxonomy } from '../hooks/useSectorTaxonomy';
import { useSphereScale } from '../hooks/useSphereViewportLayout';
import { useTranslation } from '../hooks/useTranslation';
import {
  isSphereViewBootstrapped,
  markSphereViewBootstrapped,
  resolveJumpSelection,
  SPHERE_NAVIGATE_EVENT,
} from '../navigation/sphereContext';
import type { AppTab } from '../navigation/appTab';
import type { SectorPathSelection, SectorTaxonomyDocument } from '../types/sectorTaxonomy';
import type { SectorLevelKey } from '../types/dojoSphere';
import {
  findSectorPathByIds,
  getSphereDefaultSelection,
} from '../utils/sectorTaxonomy';
import './DojoSphereView.css';

interface DojoSphereViewProps {
  onNavigateTab?: (tab: AppTab) => void;
}

function resolveFallbackSelection(taxonomy: SectorTaxonomyDocument): SectorPathSelection {
  const persisted = readPersistedSphereSelection();
  if (persisted && findSectorPathByIds(taxonomy, persisted)) {
    return persisted;
  }
  return getSphereDefaultSelection(taxonomy);
}

export function DojoSphereView({ onNavigateTab }: DojoSphereViewProps) {
  const { t } = useTranslation();
  const { taxonomy, loading, error } = useSectorTaxonomy();
  const [selection, setSelection] = useState<SectorPathSelection | null>(null);
  const [scopeLevel, setScopeLevel] = useState<SectorLevelKey>(readPersistedSphereScopeLevel);
  const [navTick, setNavTick] = useState(0);
  const viewRef = useRef<HTMLElement>(null);
  const scaleVars = useSphereScale(viewRef);

  useEffect(() => {
    const onNavigate = () => setNavTick((tick) => tick + 1);
    window.addEventListener(SPHERE_NAVIGATE_EVENT, onNavigate);
    return () => window.removeEventListener(SPHERE_NAVIGATE_EVENT, onNavigate);
  }, []);

  useEffect(() => {
    if (!taxonomy) return;

    const jumpSelection = resolveJumpSelection(taxonomy);
    if (jumpSelection) {
      setSelection(jumpSelection);
      setScopeLevel('L3');
      markSphereViewBootstrapped();
      return;
    }

    if (isSphereViewBootstrapped()) {
      const persisted = readPersistedSphereSelection();
      if (persisted && findSectorPathByIds(taxonomy, persisted)) {
        setSelection(persisted);
        setScopeLevel(readPersistedSphereScopeLevel());
        return;
      }
      setSelection((current) => current ?? resolveFallbackSelection(taxonomy));
      return;
    }

    setSelection(resolveFallbackSelection(taxonomy));
    markSphereViewBootstrapped();
  }, [taxonomy, navTick]);

  useEffect(() => {
    if (selection) persistSphereViewState(selection, scopeLevel);
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
      <section className="dojo-sphere-view dojo-sphere-view--loading">
        <LoadingIndicator label={t('sphere.loading')} variant="page" />
      </section>
    );
  }

  if ((error && !taxonomy) || !taxonomy || !selection || !path) {
    return (
      <section className="dojo-sphere-view dojo-sphere-view--error">
        <p>{error ?? t('sphere.loadFailed')}</p>
      </section>
    );
  }

  return (
    <section
      ref={viewRef}
      className="dojo-sphere-view"
      aria-label="DojoSphere"
      style={scaleVars as CSSProperties}
    >
      <div className="dojo-sphere-view__grid">
        <SphereSectorHero
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
          <SphereBottomPanel selection={selection} scope={scopeLevel} onNavigateTab={onNavigateTab} />
        ) : null}
      </div>
    </section>
  );
}
