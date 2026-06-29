import { useTranslation } from '../../hooks/useTranslation';
import type { CoreAssetSnapshot, CoreSectorOption, CoreTickerSearchItem } from '../../types/dojoCore';
import type { SectorLevelKey } from '../../types/dojoSphere';
import type { SectorPathSelection, SectorTaxonomyDocument } from '../../types/sectorTaxonomy';
import { formatCompactNumber } from '../../utils/coreCharts';
import { activeClassificationRole, findSectorOptionIndex } from '../../utils/coreSectorOptions';
import { CORE_METRIC_COLUMN_COUNT } from '../../utils/coreKeyMetrics';
import { MARKET_FLAG_IMAGE } from '../../utils/marketDisplay';
import { CoreAddToFolioButton } from './CoreAddToFolioButton';
import { CoreSectorCycleButton } from './CoreSectorCycleButton';
import { CoreSectorToolbar } from './CoreSectorToolbar';
import { CoreTickerSearch } from './CoreTickerSearch';

interface CoreAssetSnapshotProps {
  asset: CoreAssetSnapshot;
  taxonomy: SectorTaxonomyDocument | null;
  selection: SectorPathSelection | null;
  sectorOptions: CoreSectorOption[];
  sectorOptionsLoading: boolean;
  onSelectionChange: (next: SectorPathSelection) => void;
  onOpenSphereLevel?: (level: SectorLevelKey) => void;
  onCycleSector: () => void;
  onTickerSelect: (item: CoreTickerSearchItem) => void;
}

function formatSigned(value: number, digits = 2): string {
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toFixed(digits)}`;
}

export function CoreAssetSnapshot({
  asset,
  taxonomy,
  selection,
  sectorOptions,
  sectorOptionsLoading,
  onSelectionChange,
  onOpenSphereLevel,
  onCycleSector,
  onTickerSelect,
}: CoreAssetSnapshotProps) {
  const { t, text } = useTranslation();
  const { quote, metricRows, market, ticker } = asset;
  const indexedMetricRows = metricRows.map((row, rowIndex) => {
    const rowStartIndex = metricRows
      .slice(0, rowIndex)
      .reduce((total, currentRow) => total + currentRow.length, 0);

    return row.map((metric, metricIndex) => ({
      metric,
      flatIndex: rowStartIndex + metricIndex,
    }));
  });

  const renderMetricCell = (metric: (typeof metricRows)[number][number], flatIndex: number) => (
    <div
      key={metric.labelKey}
      className={[
        'core-snapshot__metric',
        flatIndex % 5 === 0 ? 'core-snapshot__metric--flat-start-5' : '',
        flatIndex % 3 === 0 ? 'core-snapshot__metric--flat-start-3' : '',
        metric.title ? 'core-snapshot__metric--truncated' : '',
      ].filter(Boolean).join(' ')}
    >
      <dt>{t(`core.metrics.${metric.labelKey}` as 'core.metrics.marketCap')}</dt>
      <dd title={metric.title}>
        {metric.value}
        {metric.subValue ? <span className="core-snapshot__metric-sub">{metric.subValue}</span> : null}
      </dd>
    </div>
  );
  const positive = quote.changePercent >= 0;
  const activeOptionIndex = findSectorOptionIndex(sectorOptions, selection);
  const classificationRole = activeClassificationRole(sectorOptions, selection);

  return (
    <header className="core-snapshot">
      <div className="core-snapshot__head">
        <div className="core-snapshot__lead">
          <div className="core-snapshot__identity">
            <img className="core-snapshot__market" src={MARKET_FLAG_IMAGE[market]} alt="" aria-hidden />
            <span className="core-snapshot__ticker">{ticker}</span>
            <h1 className="core-snapshot__name">{text(asset.name)}</h1>
          </div>
          <div className="core-snapshot__quote">
            <span className={`core-snapshot__price ${positive ? 'core-snapshot__price--up' : 'core-snapshot__price--down'}`}>
              {formatCompactNumber(quote.price)}
            </span>
            <span className={`core-snapshot__change ${positive ? 'core-snapshot__change--up' : 'core-snapshot__change--down'}`}>
              {formatSigned(quote.change)} ({formatSigned(quote.changePercent)}%)
            </span>
          </div>
          <CoreAddToFolioButton ticker={ticker} market={market} />
        </div>

        <div className="core-snapshot__controls">
          <div className="core-snapshot__controls-row">
            {taxonomy && selection ? (
              <CoreSectorToolbar
                taxonomy={taxonomy}
                selection={selection}
                classificationRole={classificationRole}
                onSelectionChange={onSelectionChange}
                onOpenSphereLevel={onOpenSphereLevel}
              />
            ) : null}
            <CoreSectorCycleButton
              options={sectorOptions}
              activeIndex={activeOptionIndex >= 0 ? activeOptionIndex : 0}
              classificationRole={classificationRole}
              loading={sectorOptionsLoading}
              onCycle={onCycleSector}
            />
            <CoreTickerSearch
              ticker={ticker}
              market={market}
              onSelect={onTickerSelect}
            />
          </div>
        </div>
      </div>

      <div
        className="core-snapshot__metrics-panel"
        style={{ '--core-metric-cols': CORE_METRIC_COLUMN_COUNT } as React.CSSProperties}
      >
        {indexedMetricRows.map((row, rowIndex) => (
          <dl key={rowIndex} className="core-snapshot__metrics-row">
            {row.map(({ metric, flatIndex }) => renderMetricCell(metric, flatIndex))}
          </dl>
        ))}
      </div>
    </header>
  );
}
