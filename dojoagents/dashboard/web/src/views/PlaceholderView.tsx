import { readSectorJumpContext } from '../navigation/sectorContext';
import './PlaceholderView.css';

interface PlaceholderViewProps {
  tab?: string;
}

export function PlaceholderView({ tab }: PlaceholderViewProps) {
  const sphereCtx = tab === 'sector' ? readSectorJumpContext() : null;

  return (
    <section className="placeholder-view" aria-label="内容区域">
      {sphereCtx ? (
        <div className="placeholder-view__sphere-hint">
          <p className="placeholder-view__sphere-title">DojoSphere</p>
          <p className="placeholder-view__sphere-sector">
            {sphereCtx.name_zh} · {sphereCtx.name_en}
          </p>
          <p className="placeholder-view__sphere-meta">
            {sphereCtx.market.toUpperCase()} · {sphereCtx.concept_code}
          </p>
        </div>
      ) : null}
    </section>
  );
}
