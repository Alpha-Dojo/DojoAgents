import { useMemo } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import type { ResolvedSectorPath, SectorPathSelection, SectorTaxonomyDocument } from '../../types/sectorTaxonomy';
import type {
  SectorLevelKey,
  SectorPerformanceResponse,
  SectorScopeMetricsResponse,
} from '../../types/dojoSphere';
import { SphereSectorMetrics } from './SphereSectorMetrics';

interface SphereSectorHeroProps {
  taxonomy: SectorTaxonomyDocument;
  selection: SectorPathSelection;
  onSelectionChange: (next: SectorPathSelection) => void;
  path: ResolvedSectorPath;
  metrics: SectorScopeMetricsResponse | null;
  metricsLoading: boolean;
  performanceByLevel: Partial<Record<SectorLevelKey, SectorPerformanceResponse>>;
  performanceLoading: boolean;
  selectedLevel: SectorLevelKey;
  onSelectLevel: (level: SectorLevelKey) => void;
}

function levelTitle(path: ResolvedSectorPath, level: SectorLevelKey, locale: 'zh' | 'en'): string {
  if (level === 'L1') {
    return locale === 'zh'
      ? path.level1.name.zh || path.level1.name.en
      : path.level1.name.en || path.level1.name.zh;
  }
  if (level === 'L2') {
    return locale === 'zh'
      ? path.level2.name.zh || path.level2.name.en
      : path.level2.name.en || path.level2.name.zh;
  }
  return locale === 'zh'
    ? path.level3.name.zh || path.level3.name.en
    : path.level3.name.en || path.level3.name.zh;
}

function levelDescription(path: ResolvedSectorPath, level: SectorLevelKey, locale: 'zh' | 'en'): string {
  if (level === 'L1') {
    return locale === 'zh'
      ? path.level1.description?.zh || path.level1.description?.en || ''
      : path.level1.description?.en || path.level1.description?.zh || '';
  }
  if (level === 'L2') {
    return locale === 'zh'
      ? path.level2.description?.zh || path.level2.description?.en || ''
      : path.level2.description?.en || path.level2.description?.zh || '';
  }
  return locale === 'zh'
    ? path.level3.definition?.zh || path.level2.description?.zh || ''
    : path.level3.definition?.en || path.level2.description?.en || '';
}

export function SphereSectorHero({
  taxonomy,
  selection,
  onSelectionChange,
  path,
  metrics,
  metricsLoading,
  performanceByLevel,
  performanceLoading,
  selectedLevel,
  onSelectLevel,
}: SphereSectorHeroProps) {
  const { locale } = useTranslation();
  const title = useMemo(() => levelTitle(path, selectedLevel, locale), [path, selectedLevel, locale]);
  const description = useMemo(
    () => levelDescription(path, selectedLevel, locale),
    [path, selectedLevel, locale],
  );

  const fullHeading = description ? `${title} · ${description}` : title;

  return (
    <article className="sphere-card sphere-sector-hero">
      <div className="sphere-sector-hero__top">
        <span className="sphere-sector-hero__icon" aria-hidden>
          🔥
        </span>
        <div className="sphere-sector-hero__main">
          <h2 className="sphere-sector-hero__heading" title={fullHeading}>
            <span className="sphere-sector-hero__title">{title}</span>
            {description ? (
              <>
                <span className="sphere-sector-hero__sep" aria-hidden>
                  ·
                </span>
                <span className="sphere-sector-hero__desc">{description}</span>
              </>
            ) : null}
          </h2>
        </div>
      </div>
      <SphereSectorMetrics
        taxonomy={taxonomy}
        selection={selection}
        onSelectionChange={onSelectionChange}
        metrics={metrics}
        metricsLoading={metricsLoading}
        performanceByLevel={performanceByLevel}
        performanceLoading={performanceLoading}
        selectedLevel={selectedLevel}
        onSelectLevel={onSelectLevel}
      />
    </article>
  );
}
