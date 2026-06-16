import type { CrossMarketLink } from '../../utils/sectorLink';
import { orderSectorsWithLink } from '../../utils/sectorLink';
import { useTranslation } from '../../hooks/useTranslation';
import type { MarketCode, MarketColumn, SectorItem, SectorMemberItem } from '../../types/dojoMesh';
import type { MarketBrandDragProps } from './DraggableMarketColumn';
import { MarketHeroCard } from './MarketHeroCard';
import { SectorBlock } from './SectorBlock';

interface MarketColumnPanelProps {
  market: MarketCode;
  flag: string;
  label: string;
  column: MarketColumn;
  chartWindowStart?: string;
  chartWindowEnd?: string;
  crossMarketLink: CrossMarketLink | null;
  lookupSector?: SectorItem | null | undefined;
  onSectorSelect?: (sector: SectorItem, market: MarketCode) => void;
  onSectorJump?: (sector: SectorItem, market: MarketCode) => void;
  onTickerClick?: (member: SectorMemberItem, market: MarketCode, sector: SectorItem) => void;
  linkedHoverDate?: string | null;
  onLinkedHoverDateChange?: (date: string | null) => void;
  brandDrag?: MarketBrandDragProps;
}

export function MarketColumnPanel({
  market,
  flag,
  label,
  column,
  chartWindowStart,
  chartWindowEnd,
  crossMarketLink,
  lookupSector,
  onSectorSelect,
  onSectorJump,
  onTickerClick,
  linkedHoverDate,
  onLinkedHoverDateChange,
  brandDrag,
}: MarketColumnPanelProps) {
  const { t } = useTranslation();
  const gainerRows = orderSectorsWithLink(
    column.gainers,
    'gain',
    crossMarketLink,
    market,
    lookupSector,
  );
  const loserRows = orderSectorsWithLink(
    column.losers,
    'loss',
    crossMarketLink,
    market,
    lookupSector,
  );

  return (
    <div className="mesh-market-column">
      <MarketHeroCard
        flag={flag}
        label={label}
        stats={column.stats}
        benchmarks={column.benchmarks}
        defaultSymbol={column.default_benchmark}
        chartWindowStart={chartWindowStart}
        chartWindowEnd={chartWindowEnd}
        linkedHoverDate={linkedHoverDate}
        onLinkedHoverDateChange={onLinkedHoverDateChange}
        brandDrag={brandDrag}
      />
      <div className="mesh-market-column__sectors">
        <SectorBlock
          variant="gain"
          title={t('sector.gainers')}
          rows={gainerRows}
          onSectorSelect={(sector) => onSectorSelect?.(sector, market)}
          onSectorJump={(sector) => onSectorJump?.(sector, market)}
          onTickerClick={(member, sector) => onTickerClick?.(member, market, sector)}
        />
        <SectorBlock
          variant="loss"
          title={t('sector.losers')}
          rows={loserRows}
          onSectorSelect={(sector) => onSectorSelect?.(sector, market)}
          onSectorJump={(sector) => onSectorJump?.(sector, market)}
          onTickerClick={(member, sector) => onTickerClick?.(member, market, sector)}
        />
      </div>
    </div>
  );
}
