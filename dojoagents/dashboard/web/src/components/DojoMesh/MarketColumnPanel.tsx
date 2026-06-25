import type { CrossMarketLink } from '../../utils/sectorLink';
import { orderSectorsWithLink } from '../../utils/sectorLink';
import { useTranslation } from '../../hooks/useTranslation';
import type { MarketCode, MarketColumn, SectorItem, SectorMemberItem } from '../../types/dojoMesh';
import type { MarketBrandDragProps } from './DraggableMarketColumn';
import { MarketHeroCard } from './MarketHeroCard';
import { SectorBlock } from './SectorBlock';

interface MarketColumnPanelProps {
  market: MarketCode;
  flagSrc: string;
  label: string;
  column: MarketColumn;
  sectorDays?: number;
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
  section?: 'all' | 'hero' | 'sectors';
}

export function MarketColumnPanel({
  market,
  flagSrc,
  label,
  column,
  sectorDays = 1,
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
  section = 'all',
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

  const showHero = section === 'all' || section === 'hero';
  const showSectors = section === 'all' || section === 'sectors';
  const scrollToLinkKey =
    crossMarketLink && market !== crossMarketLink.sourceMarket
      ? crossMarketLink.linkKey
      : null;

  return (
    <div
      className={`mesh-market-column${
        section === 'hero' ? ' mesh-market-column--hero' : ''
      }${section === 'sectors' ? ' mesh-market-column--sectors' : ''}`}
    >
      {showHero ? (
        <MarketHeroCard
          flagSrc={flagSrc}
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
      ) : null}
      {showSectors ? (
        <div className="mesh-market-column__sectors">
          <SectorBlock
            market={market}
            variant="gain"
            lookbackDays={sectorDays}
            title={t('sector.gainers')}
            rows={gainerRows}
            scrollToLinkKey={scrollToLinkKey}
            onSectorSelect={(sector) => onSectorSelect?.(sector, market)}
            onSectorJump={(sector) => onSectorJump?.(sector, market)}
            onTickerClick={(member, sector) => onTickerClick?.(member, market, sector)}
          />
          <SectorBlock
            market={market}
            variant="loss"
            lookbackDays={sectorDays}
            title={t('sector.losers')}
            rows={loserRows}
            scrollToLinkKey={scrollToLinkKey}
            onSectorSelect={(sector) => onSectorSelect?.(sector, market)}
            onSectorJump={(sector) => onSectorJump?.(sector, market)}
            onTickerClick={(member, sector) => onTickerClick?.(member, market, sector)}
          />
        </div>
      ) : null}
    </div>
  );
}
